"""GPS position and navigation destination, only when the Location option is on for the car."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .coordinator import VigieCoordinator
from .entity import VigieEntity, add_when_available
from .helpers import destination, location

PARALLEL_UPDATES = 0

LOCATION = EntityDescription(key="location", translation_key="location")
# Tracker of the navigation destination: zone triggers fire when a drive to that zone starts.
DESTINATION = EntityDescription(key="destination", translation_key="destination")


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
        add_when_available(
            coordinator,
            [DESTINATION],
            lambda d, data: bool(data.options.get("location")) and "navigation" in data.state,
            VigieDestination,
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


class VigieDestination(VigieEntity, TrackerEntity):
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: VigieCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def available(self) -> bool:
        return super().available and destination(self.data) is not None

    @property
    def latitude(self) -> float | None:
        pos = destination(self.data)
        return pos[0] if pos else None

    @property
    def longitude(self) -> float | None:
        pos = destination(self.data)
        return pos[1] if pos else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        name = self.data.value("DestinationName")
        return {"destination_name": name if isinstance(name, str) and name else None}
