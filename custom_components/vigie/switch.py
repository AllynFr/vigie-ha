"""Switches: charging, Sentry Mode, heated steering wheel."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .const import ABILITY_ACCESS, ABILITY_CHARGE, ABILITY_COMFORT
from .coordinator import VigieCoordinator, VigieData
from .entity import VigieEntity
from .helpers import CHARGING, charge_state, num, sentry_on

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class VigieSwitchDescription(SwitchEntityDescription):
    ability: str
    value_fn: Callable[[VigieData], bool | None]
    on: tuple[str, dict[str, Any] | None]
    off: tuple[str, dict[str, Any] | None]


def _charging(data: VigieData) -> bool | None:
    state = charge_state(data)
    return None if state is None else state in CHARGING


def _wheel(data: VigieData) -> bool | None:
    level = num(data, "HvacSteeringWheelHeatLevel")
    return None if level is None else level > 0


SWITCHES: tuple[VigieSwitchDescription, ...] = (
    VigieSwitchDescription(
        key="charge",
        translation_key="charge",
        ability=ABILITY_CHARGE,
        value_fn=_charging,
        on=("charge_start", None),
        off=("charge_stop", None),
    ),
    VigieSwitchDescription(
        key="sentry_mode",
        translation_key="sentry_mode",
        ability=ABILITY_ACCESS,
        value_fn=sentry_on,
        on=("sentry", {"on": True}),
        off=("sentry", {"on": False}),
    ),
    VigieSwitchDescription(
        key="steering_wheel_heater",
        translation_key="steering_wheel_heater",
        ability=ABILITY_COMFORT,
        value_fn=_wheel,
        on=("wheel_heater", {"on": True}),
        off=("wheel_heater", {"on": False}),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        VigieSwitch(coordinator, d)
        for coordinator in runtime.coordinators.values()
        for d in SWITCHES
        if runtime.can(coordinator, d.ability)
    )


class VigieSwitch(VigieEntity, SwitchEntity):
    entity_description: VigieSwitchDescription

    def __init__(self, coordinator: VigieCoordinator, description: VigieSwitchDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send(*self.entity_description.on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(*self.entity_description.off)
