"""Entities: creation by abilities/options, values, availability, dynamic fields."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.vigie.const import DOMAIN

from .conftest import API, FakeVigie, make_entry, unique_key as _key

ALL = ["lecture", "charge", "confort", "acces"]
CONTROL_DOMAINS = ("switch", "number", "climate", "lock", "button", "select")


async def _setup(hass: HomeAssistant, abilities: list[str] | None = None, signal: bool = False):
    entry = make_entry(abilities, signal)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entities(hass: HomeAssistant, entry) -> dict[str, er.RegistryEntry]:
    registry = er.async_get(hass)
    return {_key(e.unique_id): e for e in er.async_entries_for_config_entry(registry, entry.entry_id)}


def _state(hass: HomeAssistant, entry, key: str):
    entity = _entities(hass, entry)[key]
    return hass.states.get(entity.entity_id)


async def test_read_only_key_has_no_controls(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    ents = _entities(hass, entry)
    domains = {e.domain for e in ents.values()}
    assert not domains & set(CONTROL_DOMAINS)
    for key in (
        "battery_level",
        "energy_remaining",
        "range",
        "battery_health",
        "battery_capacity",
        "battery_cycles",
        "cell_gap",
        "battery_temp_min",
        "battery_temp_max",
        "pack_voltage",
        "pack_current",
        "pack_power",
        "charging_power",
        "charge_energy_added",
        "last_charge_energy",
        "energy_charged_total",
        "charge_state",
        "odometer",
        "inside_temperature",
        "outside_temperature",
        "tyre_pressure_front_left",
        "tyre_pressure_rear_right",
        "last_seen",
        "charge_limit",
        "charge_current",
        "online",
        "charging",
        "plugged_in",
        "locked",
        "doors",
        "frunk",
        "trunk",
        "windows",
        "sentry",
        "climate",
        "location",
    ):
        assert key in ents, key


async def test_sensor_values(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass)
    assert _state(hass, entry, "battery_level").state == "58.3"
    assert _state(hass, entry, "energy_remaining").state == "33.38"
    assert _state(hass, entry, "battery_health").state == "91.9"
    assert _state(hass, entry, "battery_cycles").state == "345"
    assert _state(hass, entry, "cell_gap").state == "4.0"
    assert _state(hass, entry, "pack_power").state == "-0.14"
    assert _state(hass, entry, "charge_state").state == "disconnected"
    assert _state(hass, entry, "charge_energy_added").state == "12.99"
    assert _state(hass, entry, "last_charge_energy").state == "23.4"
    assert _state(hass, entry, "last_charge_energy").attributes["max_power_kw"] == 7.4
    total = _state(hass, entry, "energy_charged_total")
    assert total.attributes["state_class"] == "total_increasing"
    assert total.attributes["device_class"] == "energy"
    assert total.attributes["unit_of_measurement"] == "kWh"
    assert _state(hass, entry, "odometer").attributes["state_class"] == "total_increasing"
    assert _state(hass, entry, "tyre_pressure_front_right").state == "2.88"
    assert _state(hass, entry, "last_seen").state == "2026-09-29T12:20:15+00:00"
    # Binary sensors
    assert _state(hass, entry, "online").state == STATE_ON
    assert _state(hass, entry, "plugged_in").state == STATE_OFF
    assert _state(hass, entry, "locked").state == STATE_OFF  # device_class lock: off = locked
    assert _state(hass, entry, "trunk").state == STATE_ON
    assert _state(hass, entry, "frunk").state == STATE_OFF
    assert _state(hass, entry, "doors").state == STATE_OFF
    assert _state(hass, entry, "windows").state == STATE_ON  # passenger window vented
    assert _state(hass, entry, "sentry").state == STATE_ON
    assert _state(hass, entry, "climate").state == STATE_OFF
    tracker = _state(hass, entry, "location")
    assert tracker.attributes["latitude"] == 48.8584
    assert tracker.attributes["source_type"] == "gps"


async def test_device_info(hass: HomeAssistant, vigie: FakeVigie) -> None:
    await _setup(hass)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "vigie.test_1")})
    assert device is not None
    assert device.manufacturer == "Tesla"
    assert device.model == "Model 3"
    assert device.name == "Tessy"
    assert device.serial_number == "5YJ••••••••••1234"
    assert device.configuration_url == "https://vigie.test/voiture"


async def test_full_key_creates_controls(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass, ALL)
    ents = _entities(hass, entry)
    for key in (
        "charge",
        "sentry_mode",
        "steering_wheel_heater",
        "climate",
        "lock",
        "open_frunk",
        "actuate_trunk",
        "wake",
        "seat_heater_left",
        "seat_heater_right",
    ):
        assert key in ents, key
    assert ents["charge_limit"].domain == "number"
    assert ents["charge_current"].domain == "number"
    assert ents["climate"].domain == "climate"
    # Read-only duplicates are replaced by the controls.
    assert ents["sentry_mode"].domain == "switch"
    assert "sentry" not in ents and "locked" not in ents
    # Signal ability cannot be probed: no horn without the option.
    assert "honk" not in ents and "flash_lights" not in ents
    # Rear seat heaters not reported by this car.
    assert "seat_heater_rear_left" not in ents
    assert hass.states.get(ents["seat_heater_left"].entity_id).state == "medium"
    assert float(hass.states.get(ents["charge_limit"].entity_id).state) == 69
    climate = hass.states.get(ents["climate"].entity_id)
    assert climate.state == "off"
    assert climate.attributes["temperature"] == 21
    assert climate.attributes["current_temperature"] == 24.5
    assert hass.states.get(ents["lock"].entity_id).state == "locked"


async def test_signal_buttons_option(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass, ["lecture"], signal=True)
    ents = _entities(hass, entry)
    assert {"honk", "flash_lights", "wake"} <= set(ents)
    assert "lock" not in ents


async def test_option_disabled_on_car_hides_controls(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.set_options(comfort=False, charge=False)
    vigie.register()
    entry = await _setup(hass, ALL)
    ents = _entities(hass, entry)
    assert "climate" not in ents or ents["climate"].domain == "binary_sensor"
    assert "seat_heater_left" not in ents
    assert ents["charge_limit"].domain == "sensor"
    assert "lock" in ents and "wake" in ents


async def test_location_option_off(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.set_options(location=False)
    del vigie.state["values"]["Location"]
    vigie.register()
    entry = await _setup(hass)
    assert "location" not in _entities(hass, entry)


async def test_asleep_availability(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    entry = await _setup(hass)
    assert _state(hass, entry, "pack_power").state != STATE_UNAVAILABLE
    vigie.state.update({"online": False, "asleep": True, "age_s": 3600})
    vigie.register()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # Live values go unavailable; last known values stay.
    for key in ("pack_power", "pack_current", "pack_voltage", "charging_power"):
        assert _state(hass, entry, key).state == STATE_UNAVAILABLE, key
    assert _state(hass, entry, "battery_level").state == "58.3"
    assert _state(hass, entry, "odometer").state != STATE_UNAVAILABLE
    assert _state(hass, entry, "online").state == STATE_OFF
    assert _state(hass, entry, "online").attributes["asleep"] is True


async def test_api_down_makes_entities_unavailable(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    entry = await _setup(hass)
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles/1/state", status=503, json={"code": "telemetry_unavailable"})
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, entry, "battery_level").state == STATE_UNAVAILABLE


async def test_new_field_adds_entity(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    del vigie.state["values"]["InsideTemp"]
    vigie.register()
    entry = await _setup(hass)
    assert "inside_temperature" not in _entities(hass, entry)
    vigie.state["values"]["InsideTemp"] = {"value": 19.5, "unit": "°C", "received_at": "2026-09-29T12:30:00Z", "age_s": 5}
    vigie.register()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _state(hass, entry, "inside_temperature").state == "19.5"


async def test_revoked_key_starts_reauth(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    entry = await _setup(hass)
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles/1/state", status=401, json={"message": "Unauthenticated."})
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" and f["context"]["entry_id"] == entry.entry_id for f in flows)


async def test_setup_revoked_key(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles", status=401, json={})
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(f["context"]["source"] == "reauth" for f in hass.config_entries.flow.async_progress())


async def test_rate_limit_is_update_failure(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    entry = await _setup(hass)
    vigie.mock.clear_requests()
    vigie.mock.get(f"{API}/vehicles/1/state", status=429, json={}, headers={"Retry-After": "30"})
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinators[1]
    assert coordinator.last_update_success is False


async def test_battery_polled_hourly(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    await _setup(hass)
    assert len(vigie.calls("GET", "/vehicles/1/battery")) == 1
    for _ in range(3):
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(vigie.calls("GET", "/vehicles/1/state")) == 4
    assert len(vigie.calls("GET", "/vehicles/1/battery")) == 1


async def test_options_change_on_car_reloads(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    entry = await _setup(hass, ALL)
    assert "climate" in _entities(hass, entry) and _entities(hass, entry)["climate"].domain == "climate"
    vigie.set_options(comfort=False)
    vigie.register()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.can(entry.runtime_data.coordinators[1], "confort") is False


async def test_refresh_service(hass: HomeAssistant, vigie: FakeVigie) -> None:
    await _setup(hass)
    before = len(vigie.calls("GET", "/vehicles/1/state"))
    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    await hass.async_block_till_done()
    assert len(vigie.calls("GET", "/vehicles/1/state")) == before + 1


async def test_unload(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass, ALL)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("DetailedChargeStateCharging", "charging"), ("DetailedChargeStateNoPower", "no_power"), ("Weird", "unknown")],
)
async def test_charge_state_decoding(hass: HomeAssistant, vigie: FakeVigie, raw: str, expected: str) -> None:
    vigie.state["values"]["DetailedChargeState"]["value"] = raw
    vigie.register()
    entry = await _setup(hass)
    assert _state(hass, entry, "charge_state").state == expected


async def test_charge_eta_and_navigation_sensors(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    entry = await _setup(hass)
    # Not charging, no destination: the sensors exist but are unavailable.
    for key in ("charge_time_remaining", "charge_end", "nav_distance_remaining", "nav_arrival", "nav_battery_at_arrival"):
        assert _state(hass, entry, key).state == STATE_UNAVAILABLE, key

    vigie.state["charge_session"].update(
        {
            "state": "Charging",
            "charging": True,
            "time_to_limit_min": 85,
            "eta": "2026-09-29T21:40:00Z",
            "target_soc": 80,
            "eta_source": "tesla",
        }
    )
    vigie.state["navigation"] = {
        "minutes_to_arrival": 41,
        "arrival": "2026-09-29T13:01:00Z",
        "distance_km": 32.2,
        "battery_at_arrival": 32,
        "traffic_delay_min": 3,
    }
    vigie.register()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    remaining = _state(hass, entry, "charge_time_remaining")
    assert remaining.state == "85"
    assert remaining.attributes["unit_of_measurement"] == "min"
    assert remaining.attributes["device_class"] == "duration"
    assert remaining.attributes["source"] == "tesla"
    assert remaining.attributes["target_soc"] == 80
    end = _state(hass, entry, "charge_end")
    assert end.state == "2026-09-29T21:40:00+00:00"
    assert end.attributes["source"] == "tesla"
    assert _state(hass, entry, "nav_distance_remaining").state == "32.2"
    assert _state(hass, entry, "nav_arrival").state == "2026-09-29T13:01:00+00:00"
    assert _state(hass, entry, "nav_battery_at_arrival").state == "32"


async def test_navigation_sensors_need_location(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.set_options(location=False)
    del vigie.state["values"]["Location"]
    vigie.register()
    entry = await _setup(hass)
    assert "nav_arrival" not in _entities(hass, entry)
    assert "charge_time_remaining" in _entities(hass, entry)


async def test_battery_level_uses_the_most_recent_of_soc_and_battery_level(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.state["values"]["BatteryLevel"] = {"value": 47.6, "unit": "%", "received_at": "2026-09-29T09:00:00Z", "age_s": 10800}
    vigie.state["values"]["Soc"] = {"value": 66.0, "unit": "%", "received_at": "2026-09-29T12:19:00Z", "age_s": 60}
    vigie.register()
    entry = await _setup(hass)
    assert _state(hass, entry, "battery_level").state == "66.0"
