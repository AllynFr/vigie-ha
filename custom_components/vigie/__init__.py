"""The Vigie integration: Tesla data and commands from a Vigie instance."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from .api import VigieAuthError, VigieClient, VigieError
from .bridge import DashboardBridge, exposed_entities
from .const import (
    ABILITY_SIGNAL,
    CONF_ABILITIES,
    CONF_LOCATION_ENTITY,
    CONF_SCAN_INTERVAL,
    CONF_SIGNAL_BUTTONS,
    CONF_VEHICLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPTION_FOR_ABILITY,
    SERVICE_REFRESH,
)
from .coordinator import VigieCoordinator
from .entity import vehicle_key
from .location import LocationReporter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_REFRESH_SCHEMA = vol.Schema({vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string])})


@dataclass
class VigieRuntimeData:
    """Objects shared by the platforms of one config entry."""

    client: VigieClient
    coordinators: dict[int, VigieCoordinator]
    abilities: set[str] = field(default_factory=set)
    # True when the API told us the abilities; False when they were probed
    # (the signal ability cannot be probed without honking).
    abilities_known: bool = False
    signal_buttons: bool = False
    location: LocationReporter | None = None
    bridge: DashboardBridge | None = None

    def can(self, coordinator: VigieCoordinator, ability: str) -> bool:
        """A control exists only if the key has the ability AND the car option is on."""
        data = coordinator.data
        if data is None or not data.options.get(OPTION_FOR_ABILITY[ability], False):
            return False
        if ability == ABILITY_SIGNAL and not self.abilities_known:
            return self.signal_buttons
        return ability in self.abilities


type VigieConfigEntry = ConfigEntry[VigieRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the vigie.refresh service."""

    async def _refresh(call: ServiceCall) -> None:
        device_ids = set(call.data.get("device_id") or [])
        wanted: set[tuple[str, str]] = set()
        if device_ids:
            registry = dr.async_get(hass)
            for device_id in device_ids:
                if device := registry.async_get(device_id):
                    wanted |= {i for i in device.identifiers if i[0] == DOMAIN}
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            for coordinator in entry.runtime_data.coordinators.values():
                if device_ids:
                    if (DOMAIN, vehicle_key(coordinator)) not in wanted:
                        continue
                await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh, schema=SERVICE_REFRESH_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: VigieConfigEntry) -> bool:
    """Set up one Vigie account (one API key)."""
    client = VigieClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_API_KEY], hass.config.language)
    try:
        body = await client.vehicles()
    except VigieAuthError as err:
        raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth") from err
    except VigieError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="update_failed",
            translation_placeholders={"error": err.code or type(err).__name__},
        ) from err

    abilities = set(entry.data.get(CONF_ABILITIES) or [])
    known = False
    if isinstance(body.get("abilities"), list):
        # Future-proof: use the key abilities if the API starts returning them.
        abilities, known = {str(a) for a in body["abilities"]}, True

    selected = {int(v) for v in entry.data.get(CONF_VEHICLES, [])}
    interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    coordinators: dict[int, VigieCoordinator] = {}
    for vehicle in body.get("data") or []:
        vid = int(vehicle["id"])
        if selected and vid not in selected:
            continue
        coordinator = VigieCoordinator(hass, entry, client, vehicle, interval)
        await coordinator.async_config_entry_first_refresh()
        coordinators[vid] = coordinator
    missing = selected - set(coordinators)
    if missing:
        _LOGGER.warning("Vehicles %s are no longer visible with this API key", sorted(missing))

    entry.runtime_data = VigieRuntimeData(
        client=client,
        coordinators=coordinators,
        abilities=abilities,
        abilities_known=known,
        signal_buttons=bool(entry.options.get(CONF_SIGNAL_BUTTONS, False)),
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if location_entity := entry.options.get(CONF_LOCATION_ENTITY):
        reporter = LocationReporter(hass, entry, client, location_entity)
        entry.runtime_data.location = reporter
        # Stopped on unload, hence on the reload that follows an options change.
        entry.async_on_unload(reporter.async_stop)
        reporter.async_start()

    # Dashboard buttons: nothing is exposed to ioDek without an explicit choice.
    if exposed := exposed_entities(entry.options):
        bridge = DashboardBridge(hass, entry, client, exposed)
        entry.runtime_data.bridge = bridge
        entry.async_on_unload(bridge.async_stop)
        bridge.async_start()
    return True


async def _async_options_updated(hass: HomeAssistant, entry: VigieConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: VigieConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
