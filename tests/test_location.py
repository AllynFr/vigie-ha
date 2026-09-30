"""Position of the user sent to ioDek (away mode of scheduled climate)."""

from __future__ import annotations

from datetime import timedelta
import json
import logging

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.vigie.const import CONF_LOCATION_ENTITY, DOMAIN
from custom_components.vigie.location import haversine_m

from .conftest import API, FakeVigie, make_entry

PERSON = "person.paul"
HOME = (43.2331, 0.0712)
# ~111 m and ~333 m north of HOME.
NEAR = (43.2341, 0.0712)
FAR = (43.2361, 0.0712)


def _post_location(vigie: FakeVigie, status: int = 200, code: str | None = None) -> None:
    body = {"ok": True, "recorded_at": "2026-09-30T06:10:00Z", "expires_at": "2026-10-01T06:10:00Z"}
    if status != 200:
        body = {"message": "x", "code": code}
    vigie.mock.post(f"{API}/me/location", status=status, json=body)


def _sent(vigie: FakeVigie) -> list[dict]:
    return vigie.calls("POST", "/me/location")


def _set(hass: HomeAssistant, pos: tuple[float, float] | None, state: str = "home", accuracy: int | None = 25) -> None:
    attrs: dict = {}
    if pos is not None:
        attrs = {"latitude": pos[0], "longitude": pos[1]}
        if accuracy is not None:
            attrs["gps_accuracy"] = accuracy
    hass.states.async_set(PERSON, state, attrs)


async def _setup(hass: HomeAssistant, entity: str | None = PERSON) -> MockConfigEntry:
    entry = make_entry()
    if entity:
        entry = MockConfigEntry(
            domain=entry.domain,
            title=entry.title,
            unique_id=entry.unique_id,
            data=entry.data,
            options={**entry.options, CONF_LOCATION_ENTITY: entity},
        )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def test_haversine() -> None:
    assert haversine_m(*HOME, *HOME) == 0
    assert 100 < haversine_m(*HOME, *NEAR) < 120
    assert 320 < haversine_m(*HOME, *FAR) < 340


async def test_initial_send(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _post_location(vigie)
    _set(hass, HOME)
    entry = await _setup(hass)
    sent = _sent(vigie)
    assert len(sent) == 1
    body = sent[0]
    assert body["latitude"] == HOME[0] and body["longitude"] == HOME[1]
    assert body["accuracy_m"] == 25
    assert body["source"] == "home_assistant"
    assert body["at"].endswith("Z") and "T" in body["at"]
    # Same authentication as the other calls.
    headers = next(h for m, u, _d, h in vigie.mock.mock_calls if str(u).endswith("/me/location"))
    assert headers["Authorization"].startswith("Bearer ")
    assert entry.runtime_data.location.sent_count == 1


async def test_no_entity_no_send(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _post_location(vigie)
    _set(hass, HOME)
    entry = await _setup(hass, entity=None)
    _set(hass, FAR)
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(hours=4))
    assert _sent(vigie) == []
    assert entry.runtime_data.location is None


async def test_missing_coordinates_ignored(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _post_location(vigie)
    _set(hass, None, state="unknown")
    await _setup(hass)
    hass.states.async_set(PERSON, "unavailable", {})
    hass.states.async_set(PERSON, "home", {"latitude": None, "longitude": 0.07})
    await hass.async_block_till_done()
    assert _sent(vigie) == []
    # First usable state is sent.
    _set(hass, HOME, accuracy=None)
    await hass.async_block_till_done()
    sent = _sent(vigie)
    assert len(sent) == 1 and "accuracy_m" not in sent[0]


async def test_move_threshold(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _post_location(vigie)
    _set(hass, HOME)
    await _setup(hass)
    await _tick(hass, freezer, timedelta(minutes=2))
    _set(hass, NEAR)
    await hass.async_block_till_done()
    assert len(_sent(vigie)) == 1
    _set(hass, FAR)
    await hass.async_block_till_done()
    sent = _sent(vigie)
    assert len(sent) == 2 and sent[1]["latitude"] == FAR[0]


async def test_one_send_per_minute(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _post_location(vigie)
    _set(hass, HOME)
    await _setup(hass)
    await _tick(hass, freezer, timedelta(seconds=10))
    _set(hass, FAR)
    await hass.async_block_till_done()
    _set(hass, (43.2400, 0.0712))
    await hass.async_block_till_done()
    assert len(_sent(vigie)) == 1
    await _tick(hass, freezer, timedelta(seconds=30))
    assert len(_sent(vigie)) == 1
    await _tick(hass, freezer, timedelta(seconds=25))
    sent = _sent(vigie)
    # Only the latest position, once, at the end of the minute.
    assert len(sent) == 2 and sent[1]["latitude"] == 43.2400
    await _tick(hass, freezer, timedelta(minutes=5))
    assert len(_sent(vigie)) == 2


async def test_refresh_every_3_hours(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _post_location(vigie)
    _set(hass, HOME)
    await _setup(hass)
    await _tick(hass, freezer, timedelta(hours=2, minutes=59))
    assert len(_sent(vigie)) == 1
    await _tick(hass, freezer, timedelta(minutes=2))
    assert len(_sent(vigie)) == 2
    await _tick(hass, freezer, timedelta(hours=3, minutes=1))
    assert len(_sent(vigie)) == 3


@pytest.mark.parametrize(
    ("status", "code", "key"),
    [(403, "ability_missing", "location_ability_missing"), (409, "location_disabled", "location_disabled")],
)
async def test_refusal_suspends(
    hass: HomeAssistant,
    vigie: FakeVigie,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    status: int,
    code: str,
    key: str,
) -> None:
    _post_location(vigie, status, code)
    _set(hass, HOME)
    caplog.set_level(logging.DEBUG, logger="custom_components.vigie")
    entry = await _setup(hass)
    assert len(_sent(vigie)) == 1
    assert entry.runtime_data.location.suspended == code
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"location_{entry.entry_id}")
    assert issue is not None and issue.translation_key == key

    await _tick(hass, freezer, timedelta(minutes=5))
    _set(hass, FAR)
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(hours=7))
    assert len(_sent(vigie)) == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "position" in r.getMessage()]
    assert len(warnings) == 1
    # Coordinates never reach the log.
    assert str(HOME[0]) not in caplog.text and str(FAR[0]) not in caplog.text

    # Changing the options reloads the entry and lifts the suspension.
    vigie.mock.clear_requests()
    vigie.register(clear=False)
    _post_location(vigie)
    hass.config_entries.async_update_entry(entry, options={**entry.options, "scan_interval": 90})
    await hass.async_block_till_done()
    assert len(_sent(vigie)) == 1
    assert entry.runtime_data.location.suspended is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"location_{entry.entry_id}") is None


async def test_rate_limit_retried_later(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _post_location(vigie, 429, "rate_limited")
    _set(hass, HOME)
    entry = await _setup(hass)
    reporter = entry.runtime_data.location
    assert reporter.suspended is None and reporter.last_error == "rate_limited"
    # No tight loop: nothing more without a change.
    await _tick(hass, freezer, timedelta(minutes=30))
    assert len(_sent(vigie)) == 1
    # A small change is enough to retry after a failure.
    vigie.mock.clear_requests()
    vigie.register(clear=False)
    _post_location(vigie)
    _set(hass, NEAR)
    await hass.async_block_till_done()
    assert len(_sent(vigie)) == 1
    assert reporter.last_error is None and reporter.sent_count == 1


async def test_unload_stops_listeners(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _post_location(vigie)
    _set(hass, HOME)
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    _set(hass, FAR)
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(hours=4))
    assert len(_sent(vigie)) == 1


async def test_diagnostics_hide_position(hass: HomeAssistant, hass_client: ClientSessionGenerator, vigie: FakeVigie) -> None:
    _post_location(vigie)
    _set(hass, HOME)
    entry = await _setup(hass)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = json.dumps(diag)
    assert str(HOME[0]) not in text and str(HOME[1]) not in text
    location = diag["location"]
    assert location["entity_id"] == PERSON
    assert location["sent_count"] == 1
    assert location["last_sent"]["latitude"] == "**REDACTED**"
    assert location["last_sent"]["longitude"] == "**REDACTED**"
    assert location["last_sent"]["accuracy_m"] == 25
