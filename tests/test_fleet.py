"""Fleet accounts: several cars on one key, each with its own options (a driver's families are reported as options)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.vigie.const import CONF_VEHICLES

from .conftest import API, FakeVigie, deep, make_entry

ALL = ["lecture", "charge", "confort", "acces"]


async def test_two_cars_two_devices_with_their_own_controls(hass: HomeAssistant, vigie: FakeVigie) -> None:
    second = deep(vigie.vehicles["data"][0])
    second.update({"id": 2, "name": "Fleet 2", "vin_masked": "LRW••••••••••0002"})
    second["options"] = {"location": False, "charge": True, "comfort": False, "access": False, "signal": False}
    second["commands"] = ["charge_start", "charge_stop", "charge_limit", "charge_amps"]
    vigie.vehicles["data"].append(second)
    state2 = deep(vigie.state)
    state2["options"] = dict(second["options"])
    state2["values"].pop("Location", None)
    vigie.register()
    vigie.mock.get(f"{API}/vehicles/2/state", json=state2)
    vigie.mock.get(f"{API}/vehicles/2/battery", json=vigie.battery)
    vigie.mock.get(f"{API}/vehicles/2/charges", json=vigie.charges)

    entry = make_entry(ALL)
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_VEHICLES: [1, 2]})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert sorted(d.name for d in devices) == ["Fleet 2", "Tessy"]

    ents = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    by_car: dict[str, dict[str, er.RegistryEntry]] = {"1": {}, "2": {}}
    for e in ents:
        for car in ("1", "2"):
            marker = f"_{car}_"
            if marker in e.unique_id:
                by_car[car][e.unique_id.split(marker, 1)[1]] = e
    assert by_car["1"]["climate"].domain == "climate"
    assert by_car["2"]["charge_limit"].domain == "number"
    assert "climate" not in by_car["2"] or by_car["2"]["climate"].domain != "climate"
    assert "lock" not in by_car["2"]
    assert "location" not in by_car["2"]
