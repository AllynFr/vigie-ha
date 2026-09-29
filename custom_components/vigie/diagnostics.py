"""Diagnostics with the key, VIN and positions masked."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import VigieConfigEntry

REDACT_ENTRY = {CONF_API_KEY}
# Positions (state values, charges, trips) and anything that could identify the car.
REDACT_DATA = {
    "vin",
    "vin_masked",
    "Location",
    "OriginLocation",
    "DestinationLocation",
    "DestinationName",
    "RouteLine",
    "location",
    "from",
    "to",
    "lat",
    "lon",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: VigieConfigEntry) -> dict[str, Any]:
    runtime = entry.runtime_data
    vehicles: list[dict[str, Any]] = []
    for coordinator in runtime.coordinators.values():
        data = coordinator.data
        vehicles.append(
            async_redact_data(
                {
                    "vehicle": coordinator.vehicle,
                    "last_update_success": coordinator.last_update_success,
                    "state": data.state if data else None,
                    "battery": data.battery if data else None,
                    "last_charge": data.last_charge if data else None,
                },
                REDACT_DATA,
            )
        )
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), REDACT_ENTRY),
            "options": dict(entry.options),
        },
        "abilities": sorted(runtime.abilities),
        "abilities_known": runtime.abilities_known,
        "vehicles": vehicles,
    }
