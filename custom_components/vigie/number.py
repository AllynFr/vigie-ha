"""Numbers: charge limit and charge current."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .const import ABILITY_CHARGE
from .coordinator import VigieCoordinator
from .entity import VigieEntity
from .helpers import num

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class VigieNumberDescription(NumberEntityDescription):
    field: str
    command: str
    body_key: str


NUMBERS: tuple[VigieNumberDescription, ...] = (
    VigieNumberDescription(
        key="charge_limit",
        translation_key="charge_limit",
        native_min_value=50,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        device_class=NumberDeviceClass.BATTERY,
        mode=NumberMode.SLIDER,
        field="ChargeLimitSoc",
        command="charge_limit",
        body_key="percent",
    ),
    VigieNumberDescription(
        key="charge_current",
        translation_key="charge_current",
        native_min_value=1,
        native_max_value=32,
        native_step=1,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=NumberDeviceClass.CURRENT,
        mode=NumberMode.SLIDER,
        field="ChargeAmps",
        command="charge_amps",
        body_key="amps",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        VigieNumber(coordinator, d)
        for coordinator in runtime.coordinators.values()
        if runtime.can(coordinator, ABILITY_CHARGE)
        for d in NUMBERS
    )


class VigieNumber(VigieEntity, NumberEntity):
    entity_description: VigieNumberDescription

    def __init__(self, coordinator: VigieCoordinator, description: VigieNumberDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def native_value(self) -> float | None:
        return num(self.data, self.entity_description.field)

    async def async_set_native_value(self, value: float) -> None:
        d = self.entity_description
        await self._send(d.command, {d.body_key: int(round(value))})
