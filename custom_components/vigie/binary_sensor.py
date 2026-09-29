"""Binary sensors: charging, plug, connectivity, locks, openings, Sentry, climate."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .const import ABILITY_ACCESS, ABILITY_COMFORT
from .coordinator import VigieCoordinator, VigieData
from .entity import VigieEntity, add_when_available
from .helpers import CHARGING, UNPLUGGED, boolean, charge_state, doors, hvac_on, sentry_on, window_open

PARALLEL_UPDATES = 0

WINDOWS = ("FdWindow", "FpWindow", "RdWindow", "RpWindow")
DOOR_KEYS = ("DriverFront", "DriverRear", "PassengerFront", "PassengerRear")


@dataclass(frozen=True, kw_only=True)
class VigieBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[VigieData], bool | None]
    exists_fn: Callable[[VigieData], bool]
    attrs_fn: Callable[[VigieData], dict[str, Any] | None] | None = None
    replaced_by_ability: str | None = None


def _charging(data: VigieData) -> bool | None:
    state = charge_state(data)
    return None if state is None else state in CHARGING


def _plugged(data: VigieData) -> bool | None:
    state = charge_state(data)
    return None if state is None else state not in UNPLUGGED


def _doors_open(data: VigieData) -> bool | None:
    d = doors(data)
    return None if d is None else any(d.get(k, False) for k in DOOR_KEYS)


def _door(key: str) -> Callable[[VigieData], bool | None]:
    def value(data: VigieData) -> bool | None:
        d = doors(data)
        return None if d is None or key not in d else d[key]

    return value


def _windows_open(data: VigieData) -> bool | None:
    states = [window_open(data, w) for w in WINDOWS]
    known = [s for s in states if s is not None]
    return any(known) if known else None


def _locked_inverted(data: VigieData) -> bool | None:
    locked = boolean(data, "Locked")
    return None if locked is None else not locked


BINARY_SENSORS: tuple[VigieBinarySensorDescription, ...] = (
    VigieBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: bool(d.state.get("online")),
        exists_fn=lambda d: True,
        attrs_fn=lambda d: {"asleep": d.asleep, "age_s": d.state.get("age_s")},
    ),
    VigieBinarySensorDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=_charging,
        exists_fn=lambda d: d.has("DetailedChargeState"),
    ),
    VigieBinarySensorDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=_plugged,
        exists_fn=lambda d: d.has("DetailedChargeState"),
    ),
    VigieBinarySensorDescription(
        key="charge_port_door",
        translation_key="charge_port_door",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda d: boolean(d, "ChargePortDoorOpen"),
        exists_fn=lambda d: d.has("ChargePortDoorOpen"),
    ),
    VigieBinarySensorDescription(
        key="fast_charger",
        translation_key="fast_charger",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: boolean(d, "FastChargerPresent"),
        exists_fn=lambda d: d.has("FastChargerPresent"),
    ),
    VigieBinarySensorDescription(
        key="battery_heater",
        translation_key="battery_heater",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda d: boolean(d, "BatteryHeaterOn"),
        exists_fn=lambda d: d.has("BatteryHeaterOn"),
    ),
    VigieBinarySensorDescription(
        # device_class LOCK: on means unlocked.
        key="locked",
        translation_key="locked",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=_locked_inverted,
        exists_fn=lambda d: d.has("Locked"),
        replaced_by_ability=ABILITY_ACCESS,
    ),
    VigieBinarySensorDescription(
        key="doors",
        translation_key="doors",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=_doors_open,
        exists_fn=lambda d: doors(d) is not None,
        attrs_fn=lambda d: {k: (doors(d) or {}).get(k) for k in DOOR_KEYS},
    ),
    VigieBinarySensorDescription(
        key="frunk",
        translation_key="frunk",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_door("TrunkFront"),
        exists_fn=lambda d: "TrunkFront" in (doors(d) or {}),
    ),
    VigieBinarySensorDescription(
        key="trunk",
        translation_key="trunk",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=_door("TrunkRear"),
        exists_fn=lambda d: "TrunkRear" in (doors(d) or {}),
    ),
    VigieBinarySensorDescription(
        key="windows",
        translation_key="windows",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=_windows_open,
        exists_fn=lambda d: any(d.has(w) for w in WINDOWS),
    ),
    VigieBinarySensorDescription(
        key="sentry",
        translation_key="sentry",
        value_fn=sentry_on,
        exists_fn=lambda d: d.has("SentryMode"),
        replaced_by_ability=ABILITY_ACCESS,
    ),
    VigieBinarySensorDescription(
        key="climate",
        translation_key="climate",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=hvac_on,
        exists_fn=lambda d: d.has("HvacPower"),
        replaced_by_ability=ABILITY_COMFORT,
    ),
    VigieBinarySensorDescription(
        key="tyre_warning",
        translation_key="tyre_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: boolean(d, "TpmsSoftWarnings"),
        exists_fn=lambda d: boolean(d, "TpmsSoftWarnings") is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    for coordinator in runtime.coordinators.values():
        descriptions = [
            d for d in BINARY_SENSORS if not (d.replaced_by_ability and runtime.can(coordinator, d.replaced_by_ability))
        ]
        add_when_available(coordinator, descriptions, lambda d, data: d.exists_fn(data), VigieBinarySensor, async_add_entities)


class VigieBinarySensor(VigieEntity, BinarySensorEntity):
    entity_description: VigieBinarySensorDescription

    def __init__(self, coordinator: VigieCoordinator, description: VigieBinarySensorDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.data)
