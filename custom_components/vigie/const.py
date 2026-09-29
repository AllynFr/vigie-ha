"""Constants for the ioDek integration (domain kept as `vigie` so existing installs keep working)."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "vigie"
MANUFACTURER: Final = "Tesla"

DEFAULT_URL: Final = "https://api.iodek.fr"
# The API answers under /api/v1 on every host (api.iodek.fr also serves /v1).
API_PREFIX: Final = "/api/v1"
SHORT_PREFIX: Final = "/v1"

CONF_VEHICLES: Final = "vehicles"
CONF_ABILITIES: Final = "abilities"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_SIGNAL_BUTTONS: Final = "signal_buttons"

DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 300

# Battery health changes at most daily; charge history a few times a day.
BATTERY_REFRESH: Final = timedelta(hours=1)
CHARGES_REFRESH: Final = timedelta(minutes=15)

# Key abilities (names used by the Vigie API).
ABILITY_READ: Final = "lecture"
ABILITY_CHARGE: Final = "charge"
ABILITY_COMFORT: Final = "confort"
ABILITY_ACCESS: Final = "acces"
ABILITY_SIGNAL: Final = "signal"
COMMAND_ABILITIES: Final = (ABILITY_CHARGE, ABILITY_COMFORT, ABILITY_ACCESS, ABILITY_SIGNAL)

# Car option (vehicle.options) required by each ability.
OPTION_FOR_ABILITY: Final = {
    ABILITY_CHARGE: "charge",
    ABILITY_COMFORT: "comfort",
    ABILITY_ACCESS: "access",
    ABILITY_SIGNAL: "signal",
}

# Commands whose validation fails on an empty body, used to detect a key's
# abilities without sending anything to the car (the API checks the ability,
# then the car option, then the body, and only then calls Tesla).
ABILITY_PROBES: Final = {
    ABILITY_CHARGE: "charge_limit",
    ABILITY_COMFORT: "set_temps",
    ABILITY_ACCESS: "sentry",
}

# Seat ids used by the seat_heater command => telemetry field.
SEAT_FIELDS: Final = {
    0: "SeatHeaterLeft",
    1: "SeatHeaterRight",
    2: "SeatHeaterRearLeft",
    4: "SeatHeaterRearCenter",
    5: "SeatHeaterRearRight",
}

SERVICE_REFRESH: Final = "refresh"
