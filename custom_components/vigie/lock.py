"""Door lock."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .const import ABILITY_ACCESS
from .coordinator import VigieCoordinator
from .entity import VigieEntity
from .helpers import boolean

PARALLEL_UPDATES = 1

LOCK = EntityDescription(key="lock", translation_key="lock")


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        VigieLock(coordinator, LOCK) for coordinator in runtime.coordinators.values() if runtime.can(coordinator, ABILITY_ACCESS)
    )


class VigieLock(VigieEntity, LockEntity):
    def __init__(self, coordinator: VigieCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def is_locked(self) -> bool | None:
        return boolean(self.data, "Locked")

    async def async_lock(self, **kwargs: Any) -> None:
        await self._send("lock")

    async def async_unlock(self, **kwargs: Any) -> None:
        await self._send("unlock")
