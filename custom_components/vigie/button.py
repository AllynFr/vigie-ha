"""Buttons: trunks, horn, lights, wake-up."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry, VigieRuntimeData
from .api import VigieError
from .const import ABILITY_ACCESS, ABILITY_SIGNAL, COMMAND_ABILITIES
from .coordinator import VigieCoordinator
from .entity import VigieEntity, command_error

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class VigieButtonDescription(ButtonEntityDescription):
    ability: str | None
    command: str | None = None


BUTTONS: tuple[VigieButtonDescription, ...] = (
    VigieButtonDescription(key="open_frunk", translation_key="open_frunk", ability=ABILITY_ACCESS, command="trunk_front"),
    VigieButtonDescription(key="actuate_trunk", translation_key="actuate_trunk", ability=ABILITY_ACCESS, command="trunk_rear"),
    VigieButtonDescription(key="honk", translation_key="honk", ability=ABILITY_SIGNAL, command="honk"),
    VigieButtonDescription(key="flash_lights", translation_key="flash_lights", ability=ABILITY_SIGNAL, command="flash"),
    # Wake-up needs any command ability, not a car option.
    VigieButtonDescription(key="wake", translation_key="wake", ability=None),
)


def _can_wake(runtime: VigieRuntimeData) -> bool:
    known = set(runtime.abilities) & set(COMMAND_ABILITIES)
    if not runtime.abilities_known and runtime.signal_buttons:
        known.add(ABILITY_SIGNAL)
    return bool(known)


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        VigieButton(coordinator, d)
        for coordinator in runtime.coordinators.values()
        for d in BUTTONS
        if (runtime.can(coordinator, d.ability) if d.ability else _can_wake(runtime))
    )


class VigieButton(VigieEntity, ButtonEntity):
    entity_description: VigieButtonDescription

    def __init__(self, coordinator: VigieCoordinator, description: VigieButtonDescription) -> None:
        super().__init__(coordinator, description)

    async def async_press(self) -> None:
        if self.entity_description.command:
            await self._send(self.entity_description.command)
            return
        try:
            await self.coordinator.client.wake(self.coordinator.vehicle_id)
        except VigieError as err:
            raise command_error(err) from err
        await self.coordinator.async_request_refresh()
