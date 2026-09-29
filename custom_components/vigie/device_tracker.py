"""GPS position, only when the Location option is on for the car."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .coordinator import VigieCoordinator
from .entity import VigieEntity, add_when_available
from .helpers import location

PARALLEL_UPDATES = 0

LOCATION = EntityDescription(key="location", translation_key="location")


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    for coordinator in entry.runtime_data.coordinators.values():
        add_when_available(
            coordinator,
            [LOCATION],
            lambda d, data: bool(data.options.get("location")) and location(data) is not None,
            VigieTracker,
            async_add_entities,
        )


class VigieTracker(VigieEntity, TrackerEntity):
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: VigieCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def available(self) -> bool:
        return super().available and location(self.data) is not None

    @property
    def latitude(self) -> float | None:
        pos = location(self.data)
        return pos[0] if pos else None

    @property
    def longitude(self) -> float | None:
        pos = location(self.data)
        return pos[1] if pos else None
