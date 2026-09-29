"""Decoding of raw Tesla values returned by the Vigie API."""

from __future__ import annotations

import json
import re
from typing import Any

from .coordinator import VigieData

_ENUM_PREFIX = re.compile(
    r"^(?:[A-Z][a-z]+)+?State(?=[A-Z])"
    r"|^(?:DefrostModeState|CabinOverheatProtectionModeState|HvacAutoModeState|ScheduledChargingMode)"
)
_CAMEL = re.compile(r"(?<!^)(?=[A-Z])")

CHARGE_STATES = ["disconnected", "no_power", "starting", "charging", "complete", "stopped", "unknown"]
CHARGING = {"starting", "charging"}
UNPLUGGED = {"disconnected", "unknown"}


def enum_value(raw: Any) -> str | None:
    """'WindowStatePartiallyOpen' -> 'PartiallyOpen' (same rule as the Vigie app)."""
    if raw is None:
        return None
    text = str(raw)
    if text == "" or text.lower() == "null":
        return None
    return _ENUM_PREFIX.sub("", text, count=1) or text


def snake(text: str) -> str:
    return _CAMEL.sub("_", text).lower()


def num(data: VigieData, name: str) -> float | None:
    value = data.value(name)
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def boolean(data: VigieData, name: str) -> bool | None:
    value = data.value(name)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
        return value.lower() in ("true", "1")
    return None


def charge_state(data: VigieData) -> str | None:
    raw = data.value("DetailedChargeState")
    if not raw:
        return None
    state = snake(str(raw).replace("DetailedChargeState", ""))
    return state if state in CHARGE_STATES else "unknown"


def fast_charging(data: VigieData) -> bool:
    return bool(boolean(data, "FastChargerPresent")) or (num(data, "DCChargingPower") or 0) > 0


def doors(data: VigieData) -> dict[str, bool] | None:
    """DoorState: JSON object {DriverFront: bool, ..., TrunkFront, TrunkRear}."""
    raw = data.value("DoorState")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None
    if not isinstance(raw, dict):
        return None
    return {k: v is True for k, v in raw.items()}


def window_open(data: VigieData, name: str) -> bool | None:
    state = enum_value(data.value(name))
    if state is None:
        return None
    return state != "Closed"


def hvac_on(data: VigieData) -> bool | None:
    state = enum_value(data.value("HvacPower"))
    if state is None:
        return None
    return state != "Off"


def sentry_on(data: VigieData) -> bool | None:
    raw = data.value("SentryMode")
    if isinstance(raw, bool):
        return raw
    state = enum_value(raw)
    if state is None:
        return None
    return state != "Off"


def location(data: VigieData) -> tuple[float, float] | None:
    raw = data.value("Location")
    if isinstance(raw, dict) and raw.get("lat") is not None and raw.get("lon") is not None:
        return float(raw["lat"]), float(raw["lon"])
    return None
