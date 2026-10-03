"""Commands: the right endpoint and body, and API errors shown to the user."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
import pytest

from .conftest import API, FakeVigie, make_entry, unique_key as _key

ALL = ["lecture", "charge", "confort", "acces"]


async def _setup(hass: HomeAssistant, vigie: FakeVigie, signal: bool = False) -> dict[str, str]:
    entry = make_entry(ALL, signal)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    return {_key(e.unique_id): e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}


def _ok(vigie: FakeVigie, command: str) -> None:
    vigie.mock.post(f"{API}/vehicles/1/commands/{command}", json={"ok": True, "message": "Done."})


@pytest.mark.parametrize(
    ("domain", "service", "key", "data", "command", "body"),
    [
        ("switch", "turn_on", "charge", {}, "charge_start", {}),
        ("switch", "turn_off", "charge", {}, "charge_stop", {}),
        ("switch", "turn_on", "sentry_mode", {}, "sentry", {"on": True}),
        ("switch", "turn_off", "sentry_mode", {}, "sentry", {"on": False}),
        ("switch", "turn_on", "steering_wheel_heater", {}, "wheel_heater", {"on": True}),
        ("number", "set_value", "charge_limit", {"value": 80}, "charge_limit", {"percent": 80}),
        ("number", "set_value", "charge_current", {"value": 13}, "charge_amps", {"amps": 13}),
        ("climate", "turn_on", "climate", {}, "climate_on", {}),
        ("climate", "set_hvac_mode", "climate", {"hvac_mode": "off"}, "climate_off", {}),
        ("climate", "set_temperature", "climate", {"temperature": 21.3}, "set_temps", {"temp": 21.5}),
        ("lock", "lock", "lock", {}, "lock", {}),
        ("lock", "unlock", "lock", {}, "unlock", {}),
        ("button", "press", "open_frunk", {}, "trunk_front", {}),
        ("button", "press", "actuate_trunk", {}, "trunk_rear", {}),
        ("select", "select_option", "seat_heater_right", {"option": "high"}, "seat_heater", {"seat": 1, "level": 3}),
        ("select", "select_option", "seat_heater_left", {"option": "off"}, "seat_heater", {"seat": 0, "level": 0}),
    ],
)
async def test_command_calls(
    hass: HomeAssistant,
    vigie: FakeVigie,
    domain: str,
    service: str,
    key: str,
    data: dict[str, Any],
    command: str,
    body: dict[str, Any],
) -> None:
    _ok(vigie, command)
    ids = await _setup(hass, vigie)
    await hass.services.async_call(domain, service, {"entity_id": ids[key], **data}, blocking=True)
    assert vigie.calls("POST", f"/vehicles/1/commands/{command}") == [body]
    # Never a wake-up behind the user's back.
    assert vigie.calls("POST", "/vehicles/1/wake") == []


async def test_signal_buttons(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _ok(vigie, "honk")
    _ok(vigie, "flash")
    ids = await _setup(hass, vigie, signal=True)
    await hass.services.async_call("button", "press", {"entity_id": ids["honk"]}, blocking=True)
    await hass.services.async_call("button", "press", {"entity_id": ids["flash_lights"]}, blocking=True)
    assert vigie.calls("POST", "/vehicles/1/commands/honk") == [{}]
    assert vigie.calls("POST", "/vehicles/1/commands/flash") == [{}]


async def test_wake_button(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.post(f"{API}/vehicles/1/wake", json={"ok": True, "state": "online", "remaining": 2})
    ids = await _setup(hass, vigie)
    await hass.services.async_call("button", "press", {"entity_id": ids["wake"]}, blocking=True)
    assert len(vigie.calls("POST", "/vehicles/1/wake")) == 1


async def test_asleep_error(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.post(
        f"{API}/vehicles/1/commands/lock",
        status=409,
        json={"message": "The car is asleep.", "code": "vehicle_asleep", "can_wake": True},
    )
    ids = await _setup(hass, vigie)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("lock", "lock", {"entity_id": ids["lock"]}, blocking=True)
    assert err.value.translation_key == "vehicle_asleep"
    assert vigie.calls("POST", "/vehicles/1/wake") == []


async def test_forbidden_error(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.post(
        f"{API}/vehicles/1/commands/charge_start",
        status=403,
        json={"message": "Charge option is off.", "code": "commands_disabled", "option": "charge"},
    )
    ids = await _setup(hass, vigie)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call("switch", "turn_on", {"entity_id": ids["charge"]}, blocking=True)
    assert err.value.translation_key == "option_disabled"


async def test_rejected_error(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.post(
        f"{API}/vehicles/1/commands/charge_start",
        status=422,
        json={"message": "Not plugged in.", "code": "command_rejected", "reason": "disconnected"},
    )
    ids = await _setup(hass, vigie)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("switch", "turn_on", {"entity_id": ids["charge"]}, blocking=True)
    assert err.value.translation_key == "command_failed"
    assert err.value.translation_placeholders == {"message": "Not plugged in."}


async def test_command_rate_limited(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.post(f"{API}/vehicles/1/commands/honk", status=429, json={}, headers={"Retry-After": "40"})
    ids = await _setup(hass, vigie, signal=True)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("button", "press", {"entity_id": ids["honk"]}, blocking=True)
    assert err.value.translation_key == "rate_limited"


async def test_number_out_of_range_rejected_locally(hass: HomeAssistant, vigie: FakeVigie) -> None:
    ids = await _setup(hass, vigie)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("number", "set_value", {"entity_id": ids["charge_limit"], "value": 40}, blocking=True)
    assert vigie.calls("POST", "/vehicles/1/commands/charge_limit") == []
