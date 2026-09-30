"""Config flow for Vigie: instance URL + API key, car selection, options, reauth."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from urllib.parse import urlparse

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from . import VigieConfigEntry
from .api import (
    VigieAuthError,
    VigieClient,
    VigieConnectionError,
    VigieError,
    VigieForbiddenError,
    VigieRateLimitError,
    normalize_url,
)
from .const import (
    ABILITY_PROBES,
    ABILITY_READ,
    CONF_ABILITIES,
    CONF_LOCATION_ENTITY,
    CONF_SCAN_INTERVAL,
    CONF_SIGNAL_BUTTONS,
    CONF_VEHICLES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_URL,
    DOMAIN,
    LOCATION_DOMAINS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class VigieConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vigie."""

    VERSION = 1

    def __init__(self) -> None:
        self._url: str = DEFAULT_URL
        self._api_key: str = ""
        self._vehicles: list[dict[str, Any]] = []
        self._abilities: list[str] | None = None

    async def _validate(self, url: str, api_key: str) -> dict[str, str]:
        """Call GET /vehicles and keep the car list. Returns form errors."""
        errors: dict[str, str] = {}
        client = VigieClient(async_get_clientsession(self.hass), url, api_key, self.hass.config.language)
        try:
            body = await client.vehicles()
        except VigieAuthError:
            errors["base"] = "invalid_auth"
        except VigieForbiddenError:
            errors["base"] = "missing_read"
        except VigieRateLimitError:
            errors["base"] = "rate_limited"
        except VigieConnectionError as err:
            _LOGGER.debug("Vigie connection failed: %s", err.code or type(err).__name__)
            errors["base"] = "cannot_connect"
        except VigieError:
            errors["base"] = "unknown"
        else:
            self._vehicles = [v for v in body.get("data") or [] if isinstance(v, dict) and "id" in v]
            self._abilities = [str(a) for a in body["abilities"]] if isinstance(body.get("abilities"), list) else None
            if not self._vehicles:
                errors["base"] = "no_vehicles"
        return errors

    async def _probe_abilities(self, vehicle_id: int) -> list[str]:
        """Detect the command abilities of the key without reaching the car."""
        if self._abilities is not None:
            return self._abilities
        client = VigieClient(async_get_clientsession(self.hass), self._url, self._api_key)
        abilities = [ABILITY_READ]
        for ability, command in ABILITY_PROBES.items():
            if await client.probe_ability(vehicle_id, ability, command):
                abilities.append(ability)
        return abilities

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._url = normalize_url(user_input[CONF_URL])
            self._api_key = user_input[CONF_API_KEY].strip()
            if not urlparse(self._url).scheme.startswith("http"):
                errors[CONF_URL] = "invalid_url"
            else:
                errors = await self._validate(self._url, self._api_key)
            if not errors:
                host = urlparse(self._url).netloc
                await self.async_set_unique_id(f"{host}:{min(int(v['id']) for v in self._vehicles)}")
                self._abort_if_unique_id_configured()
                return await self.async_step_vehicles()

        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default=self._url): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Required(CONF_API_KEY): KEY_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_vehicles(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = [int(v) for v in user_input[CONF_VEHICLES]]
            if not selected:
                errors["base"] = "no_selection"
            else:
                abilities = await self._probe_abilities(selected[0])
                names = [str(v.get("name") or f"Tesla {v['id']}") for v in self._vehicles if int(v["id"]) in selected]
                return self.async_create_entry(
                    title=", ".join(names),
                    data={
                        CONF_URL: self._url,
                        CONF_API_KEY: self._api_key,
                        CONF_VEHICLES: selected,
                        CONF_ABILITIES: abilities,
                    },
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL, CONF_SIGNAL_BUTTONS: False},
                )

        options = [
            SelectOptionDict(value=str(v["id"]), label=f"{v.get('name') or 'Tesla'} ({v.get('vin_masked', '')})")
            for v in self._vehicles
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_VEHICLES, default=[o["value"] for o in options]): SelectSelector(
                    SelectSelectorConfig(options=options, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="vehicles", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._url = entry_data[CONF_URL]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY].strip()
            errors = await self._validate(self._url, self._api_key)
            if not errors:
                visible = {int(v["id"]) for v in self._vehicles}
                selected = [int(v) for v in entry.data.get(CONF_VEHICLES, [])]
                if not set(selected) & visible:
                    return self.async_abort(reason="wrong_account")
                abilities = await self._probe_abilities(next(v for v in selected if v in visible))
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: self._api_key, CONF_ABILITIES: abilities},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): KEY_SELECTOR}),
            errors=errors,
            description_placeholders={"url": self._url},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: VigieConfigEntry) -> OptionsFlow:
        return VigieOptionsFlow()


class VigieOptionsFlow(OptionsFlow):
    """Polling interval, signal buttons and position sent to ioDek."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            data: dict[str, Any] = {
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_SIGNAL_BUTTONS: bool(user_input.get(CONF_SIGNAL_BUTTONS, False)),
            }
            if location_entity := user_input.get(CONF_LOCATION_ENTITY):
                data[CONF_LOCATION_ENTITY] = location_entity
            return self.async_create_entry(data=data)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(CONF_SIGNAL_BUTTONS, default=options.get(CONF_SIGNAL_BUTTONS, False)): BooleanSelector(),
                # Optional and empty by default: nothing is sent without a choice.
                vol.Optional(
                    CONF_LOCATION_ENTITY, description={"suggested_value": options.get(CONF_LOCATION_ENTITY)}
                ): EntitySelector(EntitySelectorConfig(domain=list(LOCATION_DOMAINS))),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
