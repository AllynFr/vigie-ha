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
CONF_LOCATION_ENTITY: Final = "location_entity"
CONF_EXPOSED_ENTITIES: Final = "exposed_entities"

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

# User position sent to ioDek for the "away" mode of scheduled climate.
LOCATION_DOMAINS: Final = ("person", "device_tracker")
LOCATION_SOURCE: Final = "home_assistant"
LOCATION_MIN_MOVE_M: Final = 200.0
LOCATION_MIN_INTERVAL: Final = timedelta(minutes=1)
# The server keeps a Home Assistant position fresh for 6 h: resend every 3 h.
LOCATION_REFRESH: Final = timedelta(hours=3)

# Dashboard buttons bridge: Home Assistant entities that ioDek dashboard buttons
# may act on. Closed list, checked on both sides (ioDek and here).
BRIDGE_SERVICES: Final[dict[str, tuple[str, ...]]] = {
    "script": ("turn_on",),
    "scene": ("turn_on",),
    "button": ("press",),
    "input_button": ("press",),
    "automation": ("trigger",),
    "switch": ("toggle", "turn_on", "turn_off"),
    "input_boolean": ("toggle", "turn_on", "turn_off"),
    "light": ("toggle", "turn_on", "turn_off"),
    "fan": ("toggle", "turn_on", "turn_off"),
    "cover": ("toggle", "open_cover", "close_cover", "stop_cover"),
    "lock": ("lock", "unlock"),
}
BRIDGE_DOMAINS: Final = tuple(BRIDGE_SERVICES)
BRIDGE_MAX_ENTITIES: Final = 100
BRIDGE_NAME_MAX: Final = 80
BRIDGE_STATE_MAX: Final = 40
BRIDGE_MESSAGE_MAX: Final = 200
# Pusher protocol (Laravel Reverb), in seconds.
BRIDGE_ACTIVITY_TIMEOUT: Final = 20
BRIDGE_PONG_TIMEOUT: Final = 10
BRIDGE_ACTION_TIMEOUT: Final = 10
BRIDGE_STATES_DELAY: Final = 1.0
BRIDGE_REPUBLISH: Final = timedelta(hours=6)
BRIDGE_RECONNECT_DELAYS: Final = (1, 2, 5, 10, 30, 60)
# A connection that stayed up this long resets the reconnect delays.
BRIDGE_STABLE_AFTER: Final = 300
# Failed publication: retried after 60 s, then less and less often.
BRIDGE_PUBLISH_RETRY_DELAYS: Final = (60, 120, 300, 600, 1800)
# Publication accepted but no real-time channel on the server side.
BRIDGE_NO_SOCKET_RETRY: Final = 300
# Action ids remembered so that one order is run once only.
BRIDGE_SEEN_ACTIONS: Final = 200
