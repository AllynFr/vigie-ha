"""Climate: cabin conditioning on/off and target temperature."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigieConfigEntry
from .const import ABILITY_COMFORT
from .coordinator import VigieCoordinator
from .entity import VigieEntity
from .helpers import hvac_on, num

PARALLEL_UPDATES = 1

CLIMATE = EntityDescription(key="climate", translation_key="climate")


async def async_setup_entry(
    hass: HomeAssistant, entry: VigieConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    runtime = entry.runtime_data
    async_add_entities(
        VigieClimate(coordinator, CLIMATE)
        for coordinator in runtime.coordinators.values()
        if runtime.can(coordinator, ABILITY_COMFORT)
    )


class VigieClimate(VigieEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT_COOL]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 15
    _attr_max_temp = 28
    _attr_target_temperature_step = 0.5
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: VigieCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator, description)

    @property
    def hvac_mode(self) -> HVACMode | None:
        on = hvac_on(self.data)
        if on is None:
            return None
        return HVACMode.HEAT_COOL if on else HVACMode.OFF

    @property
    def current_temperature(self) -> float | None:
        return num(self.data, "InsideTemp")

    @property
    def target_temperature(self) -> float | None:
        return num(self.data, "HvacLeftTemperatureRequest")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._send("climate_off" if hvac_mode == HVACMode.OFF else "climate_on")

    async def async_turn_on(self) -> None:
        await self._send("climate_on")

    async def async_turn_off(self) -> None:
        await self._send("climate_off")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._send("set_temps", {"temp": round(float(temp) * 2) / 2})
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self.async_set_hvac_mode(mode)
