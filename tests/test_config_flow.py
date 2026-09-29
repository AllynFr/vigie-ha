"""Config flow, options flow and reauthentication."""

from __future__ import annotations

from http import HTTPStatus

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.vigie.const import CONF_ABILITIES, CONF_SCAN_INTERVAL, CONF_SIGNAL_BUTTONS, DOMAIN

from .conftest import API, KEY, URL, FakeVigie, make_entry

PROBES = ("charge_limit", "set_temps", "sentry")


def _probe(vigie: FakeVigie, status: int, code: str | None) -> None:
    for command in PROBES:
        vigie.mock.post(
            f"{API}/vehicles/1/commands/{command}",
            status=status,
            json={"message": "x", "code": code} if code else {"message": "The percent field is required.", "errors": {}},
        )


async def _start(hass: HomeAssistant, key: str = KEY) -> dict:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL + "/", "api_key": key})


async def test_flow_read_only_key(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _probe(vigie, HTTPStatus.FORBIDDEN, "ability_missing")
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "vehicles"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"vehicles": ["1"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Tessy"
    assert result["data"]["url"] == URL
    assert result["data"]["vehicles"] == [1]
    assert result["data"][CONF_ABILITIES] == ["lecture"]
    assert result["options"][CONF_SCAN_INTERVAL] == 60
    assert result["result"].unique_id == "vigie.test:1"
    # Probes were sent with an empty body, never with a real value.
    assert vigie.calls("POST", "/vehicles/1/commands/charge_limit") == [{}]


async def test_flow_full_key(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _probe(vigie, HTTPStatus.UNPROCESSABLE_ENTITY, None)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"vehicles": ["1"]})
    assert result["data"][CONF_ABILITIES] == ["lecture", "charge", "confort", "acces"]


async def test_flow_option_disabled_still_means_ability(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _probe(vigie, HTTPStatus.FORBIDDEN, "option_disabled")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"vehicles": ["1"]})
    assert result["data"][CONF_ABILITIES] == ["lecture", "charge", "confort", "acces"]


async def test_flow_uses_api_abilities_when_given(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.vehicles["abilities"] = ["lecture", "signal"]
    vigie.register()
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"vehicles": ["1"]})
    assert result["data"][CONF_ABILITIES] == ["lecture", "signal"]
    assert vigie.calls("POST", "/vehicles/1/commands/charge_limit") == []


async def _error_case(hass: HomeAssistant, vigie: FakeVigie, status: int, body: dict, expected: str) -> None:
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles", status=status, json=body, headers={"Retry-After": "12"})
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_flow_invalid_key(hass: HomeAssistant, vigie: FakeVigie) -> None:
    await _error_case(hass, vigie, 401, {"message": "Unauthenticated."}, "invalid_auth")


async def test_flow_missing_read(hass: HomeAssistant, vigie: FakeVigie) -> None:
    await _error_case(hass, vigie, 403, {"code": "ability_missing", "ability": "lecture"}, "missing_read")


async def test_flow_rate_limited(hass: HomeAssistant, vigie: FakeVigie) -> None:
    await _error_case(hass, vigie, 429, {"message": "Too Many Attempts."}, "rate_limited")


async def test_flow_server_error(hass: HomeAssistant, vigie: FakeVigie) -> None:
    await _error_case(hass, vigie, 500, {"message": "boom"}, "cannot_connect")


async def test_flow_no_vehicles(hass: HomeAssistant, vigie: FakeVigie) -> None:
    await _error_case(hass, vigie, 200, {"data": []}, "no_vehicles")


async def test_flow_recovers_after_error(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles", status=401, json={})
    result = await _start(hass, "bad")
    assert result["errors"] == {"base": "invalid_auth"}
    vigie.register()
    _probe(vigie, 403, "ability_missing")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"url": URL, "api_key": KEY})
    assert result["step_id"] == "vehicles"


async def test_flow_already_configured(hass: HomeAssistant, vigie: FakeVigie) -> None:
    make_entry().add_to_hass(hass)
    result = await _start(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    _probe(vigie, 422, None)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "3|vigie_new"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_key"] == "3|vigie_new"
    assert entry.data[CONF_ABILITIES] == ["lecture", "charge", "confort", "acces"]


async def test_reauth_invalid_then_wrong_account(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles", status=401, json={})
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "bad"})
    assert result["errors"] == {"base": "invalid_auth"}
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles", json={"data": [{"id": 9, "name": "Other", "vin_masked": "x", "options": {}}]})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"api_key": "4|vigie_other"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data["api_key"] == KEY


async def test_options_flow(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 120, CONF_SIGNAL_BUTTONS: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_SCAN_INTERVAL: 120, CONF_SIGNAL_BUTTONS: True}
    coordinator = entry.runtime_data.coordinators[1]
    assert coordinator.update_interval.total_seconds() == 120
