"""Selects: seat heaters (off, low, medium, high)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .const import ABILITY_COMFORT, SEAT_FIELDS
from .coordinator import VigieCoordinator, VigieData
from .entity import VigieEntity, add_when_available
from .helpers import num

PARALLEL_UPDATES = 1

LEVELS = ["off", "low", "medium", "high"]

SEAT_KEYS = {
    0: "seat_heater_left",
    1: "seat_heater_right",
    2: "seat_heater_rear_left",
    4: "seat_heater_rear_center",
    5: "seat_heater_rear_right",
}


@dataclass(frozen=True, kw_only=True)
class VigieSeatDescription(SelectEntityDescription):
    seat: int
    field: str
    front: bool


SEATS = tuple(
    VigieSeatDescription(
        key=key,
        translation_key=key,
        options=LEVELS,
        seat=seat,
        field=SEAT_FIELDS[seat],
        front=seat in (0, 1),
    )
    for seat, key in SEAT_KEYS.items()
)


def _exists(description: VigieSeatDescription, data: VigieData) -> bool:
    # Front seats always; rear seats once the car reports them (not all trims have them).
    return description.front or data.has(description.field)


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    for coordinator in runtime.coordinators.values():
        if runtime.can(coordinator, ABILITY_COMFORT):
            add_when_available(coordinator, SEATS, _exists, VigieSeatSelect, async_add_entities)


class VigieSeatSelect(VigieEntity, SelectEntity):
    entity_description: VigieSeatDescription

    def __init__(self, coordinator: VigieCoordinator, description: VigieSeatDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def current_option(self) -> str | None:
        level = num(self.data, self.entity_description.field)
        if level is None:
            return None
        return LEVELS[max(0, min(3, int(round(level))))]

    async def async_select_option(self, option: str) -> None:
        await self._send("seat_heater", {"seat": self.entity_description.seat, "level": LEVELS.index(option)})
