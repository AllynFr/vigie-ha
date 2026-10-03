"""Base entity and helpers for Vigie."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import (
    VigieAsleepError,
    VigieAuthError,
    VigieError,
    VigieForbiddenError,
    VigieRateLimitError,
    app_url,
)
from .const import DOMAIN, MANUFACTURER
from .coordinator import VigieCoordinator, VigieData


def vehicle_identifier(base_url: str, vehicle_id: int) -> str:
    """Stable prefix: instance host + Vigie vehicle id (device identifier and unique_id prefix)."""
    host = base_url.split("://", 1)[-1]
    return f"{host}_{vehicle_id}"


def vehicle_key(coordinator: VigieCoordinator) -> str:
    return vehicle_identifier(coordinator.client.base_url, coordinator.vehicle_id)


def electricity_key(entry: ConfigEntry, base_url: str) -> str:
    """Identifier of the account's electricity device (one per config entry)."""
    host = base_url.split("://", 1)[-1]
    return f"{host}_electricity_{entry.unique_id or entry.entry_id}"


class VigieEntity(CoordinatorEntity[VigieCoordinator]):
    """Common base: one device per car, unique_id = host_vehicle_key."""

    _attr_has_entity_name = True
    # Live values (power, current...) are stale once the car sleeps.
    _live: bool = False

    def __init__(self, coordinator: VigieCoordinator, description: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{vehicle_key(coordinator)}_{description.key}"
        vehicle = coordinator.vehicle
        battery = (coordinator.data.battery if coordinator.data else None) or {}
        pack = battery.get("pack") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vehicle_key(coordinator))},
            manufacturer=MANUFACTURER,
            model=pack.get("model"),
            model_id=pack.get("variant"),
            name=vehicle.get("name") or f"Tesla {coordinator.vehicle_id}",
            serial_number=vehicle.get("vin_masked"),
            configuration_url=f"{app_url(coordinator.client.base_url)}/voiture",
        )

    @property
    def data(self) -> VigieData:
        return self.coordinator.data

    @property
    def available(self) -> bool:
        if not super().available or self.coordinator.data is None:
            return False
        if self._live and self.data.asleep:
            return False
        return True

    async def _send(self, command: str, body: dict[str, Any] | None = None) -> None:
        """Send a command and translate API errors for the UI."""
        try:
            await self.coordinator.client.command(self.coordinator.vehicle_id, command, body)
        except VigieError as err:
            raise command_error(err) from err
        await self.coordinator.async_request_refresh()


def command_error(err: VigieError) -> HomeAssistantError:
    """Map a Vigie API error to a translated Home Assistant error."""
    placeholders = {"message": err.message or err.code or ""}
    if isinstance(err, VigieAsleepError):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="vehicle_asleep")
    if isinstance(err, VigieForbiddenError):
        key = "ability_missing" if err.code == "ability_missing" else "option_disabled"
        return ServiceValidationError(translation_domain=DOMAIN, translation_key=key, translation_placeholders=placeholders)
    if isinstance(err, VigieRateLimitError):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="rate_limited")
    if isinstance(err, VigieAuthError):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="invalid_auth")
    return HomeAssistantError(translation_domain=DOMAIN, translation_key="command_failed", translation_placeholders=placeholders)


def add_when_available(
    coordinator: VigieCoordinator,
    descriptions: Iterable[Any],
    exists: Callable[[Any, VigieData], bool],
    factory: Callable[[VigieCoordinator, Any], Entity],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add entities whose data exists now, and the others once the car reports them.

    Tesla only sends a field when it changes, so a field can appear days after setup.
    """
    pending = list(descriptions)

    @callback
    def _check() -> None:
        data = coordinator.data
        if data is None:
            return
        ready = [d for d in pending if exists(d, data)]
        if not ready:
            return
        for d in ready:
            pending.remove(d)
        async_add_entities([factory(coordinator, d) for d in ready])

    _check()
    if pending:
        coordinator.config_entry.async_on_unload(coordinator.async_add_listener(_check))
