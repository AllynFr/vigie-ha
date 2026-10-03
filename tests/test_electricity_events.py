"""Electricity of the account, charge plan sensors, car events (vigie_event) and device triggers."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed, async_get_device_automations

from custom_components.vigie.bridge import DashboardBridge
from custom_components.vigie.const import DOMAIN, EVENT_TYPES, EVENT_VIGIE

from .conftest import API, FakeVigie, make_entry, unique_key
from .test_bridge import AUTH, SOCKET, FakeWS, _publish, _until

CAR = "vigie.test_1"


async def _setup(hass: HomeAssistant, abilities: list[str] | None = None):
    entry = make_entry(abilities)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _ids(hass: HomeAssistant, entry) -> dict[str, str]:
    registry = er.async_get(hass)
    return {unique_key(e.unique_id): e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}


def _state(hass: HomeAssistant, entry, key: str):
    return hass.states.get(_ids(hass, entry)[key])


def _car_device(hass: HomeAssistant) -> dr.DeviceEntry:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, CAR)})
    assert device is not None
    return device


def _capture(hass: HomeAssistant) -> list[Event]:
    events: list[Event] = []

    @callback
    def _listener(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(EVENT_VIGIE, _listener)
    return events


# Electricity


async def test_electricity_sensors_on_the_account_device(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass)
    price = _state(hass, entry, "electricity_price")
    assert float(price.state) == pytest.approx(0.1921)
    assert price.attributes["unit_of_measurement"] == "EUR/kWh"
    assert price.attributes["tariff"] == "tempo"
    assert price.attributes["period"] == "peak"
    assert price.attributes["place"] == "Maison"
    assert price.attributes["place_source"] == "default"
    assert _state(hass, entry, "electricity_period").state == "peak"
    assert _state(hass, entry, "electricity_period").attributes["options"] == ["base", "peak", "offpeak", "free"]
    assert _state(hass, entry, "electricity_next_change").state == "2026-10-06T20:00:00+00:00"
    assert _state(hass, entry, "electricity_next_change").attributes["period"] == "offpeak"
    assert float(_state(hass, entry, "electricity_next_price").state) == pytest.approx(0.1536)
    assert _state(hass, entry, "tempo_today").state == "white"
    # Tomorrow's colour not published yet.
    assert _state(hass, entry, "tempo_tomorrow").state == "unknown"
    assert _state(hass, entry, "tempo_tomorrow").attributes["options"] == ["blue", "white", "red", "unknown"]

    registry = er.async_get(hass)
    device_id = registry.async_get(_ids(hass, entry)["electricity_price"]).device_id
    device = dr.async_get(hass).async_get(device_id)
    assert device.name == "ioDek Electricity"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.id != _car_device(hass).id


async def test_electricity_read_every_5_minutes(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    await _setup(hass)
    assert len(vigie.calls("GET", "/energy")) == 1
    for _ in range(4):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(vigie.calls("GET", "/energy")) == 1
    assert len(vigie.calls("GET", "/vehicles/1/state")) == 5
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(vigie.calls("GET", "/energy")) == 2


async def test_older_iodek_without_the_new_routes(hass: HomeAssistant, aioclient_mock) -> None:
    fake = FakeVigie(aioclient_mock)
    aioclient_mock.get(f"{API}/energy", status=404, json={"message": "Not found"})
    aioclient_mock.get(f"{API}/vehicles/1/charge-plan", status=404, json={"message": "Not found"})
    fake.register(clear=False)
    entry = await _setup(hass)
    keys = _ids(hass, entry)
    assert "battery_level" in keys
    assert not [k for k in keys if k.startswith(("electricity_", "tempo_", "charge_plan_"))]
    # The route is not asked again.
    await entry.runtime_data.coordinators[1].async_refresh()
    assert len(fake.calls("GET", "/vehicles/1/charge-plan")) == 1


# Charge plan


async def test_charge_plan_sensors(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass)
    status = _state(hass, entry, "charge_plan_status")
    assert status.state == "planned"
    assert status.attributes["planner_enabled"] is True
    assert status.attributes["departure"] == "2026-10-07T05:30:00Z"
    assert status.attributes["energy_kwh"] == 24.5
    assert _state(hass, entry, "charge_plan_start").state == "2026-10-06T21:00:00+00:00"
    assert _state(hass, entry, "charge_plan_end").state == "2026-10-07T01:15:00+00:00"
    target = _state(hass, entry, "charge_plan_target")
    assert target.state == "80"
    assert target.attributes["unit_of_measurement"] == "%"
    assert _state(hass, entry, "charge_plan_reason").state == "calendar"
    # Plan sensors belong to the car.
    registry = er.async_get(hass)
    assert registry.async_get(_ids(hass, entry)["charge_plan_status"]).device_id == _car_device(hass).id


async def test_no_plan_and_idle_planner_read_every_15_minutes(
    hass: HomeAssistant, aioclient_mock, freezer: FrozenDateTimeFactory
) -> None:
    fake = FakeVigie(aioclient_mock)
    aioclient_mock.get(f"{API}/vehicles/1/charge-plan", json={"vehicle_id": 1, "planner_enabled": False, "plan": None})
    fake.register(clear=False)
    entry = await _setup(hass)
    assert _state(hass, entry, "charge_plan_status").state == "no_plan"
    for key in ("charge_plan_start", "charge_plan_end", "charge_plan_target", "charge_plan_reason"):
        assert _state(hass, entry, key).state == STATE_UNKNOWN
    assert len(fake.calls("GET", "/vehicles/1/charge-plan")) == 1
    for _ in range(14):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(fake.calls("GET", "/vehicles/1/charge-plan")) == 1
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(fake.calls("GET", "/vehicles/1/charge-plan")) == 2


async def test_active_planner_read_with_the_state(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    await _setup(hass)
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(vigie.calls("GET", "/vehicles/1/charge-plan")) == 2


# Events


async def test_event_fired_with_the_car_device(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie)
    entry = await _setup(hass, ["lecture", "domotique"])
    bridge = entry.runtime_data.bridge
    assert bridge is not None and bridge.entities == []
    events = _capture(hass)
    data = {
        "type": "sentry_alert",
        "vehicle_id": 1,
        "vehicle_name": "Tessy",
        "at": "2026-10-06T10:19:30Z",
        "level": "panic",
        "location": {"lat": 45.76, "lon": 4.84},
        "unexpected": "dropped",
    }
    assert bridge.async_fire_event(data) is True
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data == {
        "type": "sentry_alert",
        "vehicle_id": 1,
        "vehicle_name": "Tessy",
        "at": "2026-10-06T10:19:30Z",
        "level": "panic",
        "location": {"lat": 45.76, "lon": 4.84},
        "device_id": _car_device(hass).id,
        "config_entry_id": entry.entry_id,
    }
    # A car of another entry, or no type: ignored.
    assert bridge.async_fire_event({"type": "parked", "vehicle_id": 2}) is False
    assert bridge.async_fire_event({"vehicle_id": 1}) is False
    assert len(events) == 1
    assert bridge.counters["events_fired"] == 1


async def test_charge_event_reads_the_car_again(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie)
    entry = await _setup(hass, ["lecture", "domotique"])
    before = len(vigie.calls("GET", "/vehicles/1/state"))
    entry.runtime_data.bridge.async_fire_event({"type": "charge_started", "vehicle_id": 1, "soc": 50})
    await hass.async_block_till_done()
    await _until(lambda: len(vigie.calls("GET", "/vehicles/1/state")) == before + 1)
    assert len(vigie.calls("GET", "/vehicles/1/charge-plan")) == 2


async def test_event_received_on_the_websocket(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie, socket=SOCKET)
    vigie.mock.post(f"{API}/ha/socket-auth", json={"auth": AUTH})
    events = _capture(hass)
    ws = FakeWS()
    connect = AsyncMock(return_value=ws)
    with patch.object(DashboardBridge, "_ws_connect", connect):
        entry = await _setup(hass, ["lecture", "domotique"])
        await _until(lambda: connect.await_count == 1)
        # No entity exposed: an empty list registers the installation.
        assert vigie.calls("PUT", "/ha/entities")[0]["entities"] == []
        ws.push("pusher:connection_established", {"socket_id": "1.2", "activity_timeout": 20})
        await _until(lambda: "pusher:subscribe" in ws.events())
        ws.push("pusher_internal:subscription_succeeded", {}, channel="private-ha.7")
        ws.push("iodek.event", {"type": "battery_low", "vehicle_id": 1, "soc": 19, "threshold": 20}, "private-ha.8")
        ws.push("iodek.event", {"type": "parked", "vehicle_id": 1, "soc": 64, "place": "Maison", "at_home": True}, "private-ha.7")
        await _until(lambda: len(events) == 1)
        assert events[0].data["type"] == "parked"
        assert events[0].data["at_home"] is True
        assert events[0].data["device_id"] == _car_device(hass).id
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_no_bridge_without_the_home_automation_permission(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass, ["lecture"])
    assert entry.runtime_data.bridge is None
    assert vigie.calls("PUT", "/ha/entities") == []


async def test_events_only_refusal_raises_no_repair(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie, status=403, code="plan_required")
    entry = await _setup(hass, ["lecture", "domotique"])
    bridge = entry.runtime_data.bridge
    await _until(lambda: bridge.suspended is not None)
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"bridge_{entry.entry_id}") is None


# Device triggers


async def test_device_triggers(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass)
    car = _car_device(hass)
    # Entity triggers of other platforms (sensor, binary_sensor) come along: keep ours.
    triggers = [
        t for t in await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, car.id) if t["domain"] == DOMAIN
    ]
    assert sorted(t["type"] for t in triggers) == sorted(EVENT_TYPES)
    assert all(t["device_id"] == car.id and t["platform"] == "device" for t in triggers)

    registry = er.async_get(hass)
    electricity = registry.async_get(_ids(hass, entry)["electricity_price"]).device_id
    others = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, electricity)
    assert [t for t in others if t["domain"] == DOMAIN] == []


async def test_device_trigger_runs_the_automation(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie)
    entry = await _setup(hass, ["lecture", "domotique"])
    car = _car_device(hass)
    calls: list[str] = []

    @callback
    def _record(event: Event) -> None:
        calls.append(event.data["what"])

    hass.bus.async_listen("test_done", _record)
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "trigger": {"platform": "device", "domain": DOMAIN, "device_id": car.id, "type": "sentry_alert"},
                    "action": {"event": "test_done", "event_data": {"what": "{{ trigger.event.data.level }}"}},
                }
            ]
        },
    )
    await hass.async_block_till_done()
    bridge = entry.runtime_data.bridge
    bridge.async_fire_event({"type": "charge_complete", "vehicle_id": 1, "soc": 80})
    bridge.async_fire_event({"type": "sentry_alert", "vehicle_id": 1, "level": "aware"})
    await hass.async_block_till_done()
    assert calls == ["aware"]
