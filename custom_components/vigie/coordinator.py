"""Per-vehicle data coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    VigieAuthError,
    VigieClient,
    VigieError,
    VigieForbiddenError,
    VigieNotFoundError,
    VigieRateLimitError,
)
from .const import BATTERY_REFRESH, CHARGES_REFRESH, DOMAIN

if TYPE_CHECKING:
    from . import VigieConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class VigieData:
    """Latest data for one vehicle."""

    state: dict[str, Any]
    battery: dict[str, Any] | None = None
    last_charge: dict[str, Any] | None = None
    charges_total: int = 0

    @property
    def values(self) -> dict[str, dict[str, Any]]:
        return self.state.get("values") or {}

    def value(self, name: str) -> Any:
        """Raw value of a telemetry field, or None."""
        item = self.values.get(name)
        return item.get("value") if isinstance(item, dict) else None

    def has(self, name: str) -> bool:
        return name in self.values

    @property
    def asleep(self) -> bool:
        return bool(self.state.get("asleep", True))

    @property
    def options(self) -> dict[str, bool]:
        return self.state.get("options") or {}


@dataclass
class _Cache:
    battery: dict[str, Any] | None = None
    battery_at: datetime | None = None
    charges: dict[str, Any] | None = None
    charges_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class VigieCoordinator(DataUpdateCoordinator[VigieData]):
    """Polls /state every interval, /battery hourly and /charges every 15 min."""

    config_entry: VigieConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VigieConfigEntry,
        client: VigieClient,
        vehicle: dict[str, Any],
        interval: int,
    ) -> None:
        self.client = client
        self.vehicle = vehicle
        self.vehicle_id: int = int(vehicle["id"])
        self._cache = _Cache()
        self._initial_options: dict[str, bool] | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} vehicle {self.vehicle_id}",
            update_interval=timedelta(seconds=interval),
        )

    async def _async_update_data(self) -> VigieData:
        now = dt_util.utcnow()
        try:
            state = await self.client.state(self.vehicle_id)
            cache = self._cache
            if cache.battery_at is None or now - cache.battery_at >= BATTERY_REFRESH:
                cache.battery = await self._optional(self.client.battery(self.vehicle_id), cache.battery)
                cache.battery_at = now
            if cache.charges_at is None or now - cache.charges_at >= CHARGES_REFRESH:
                cache.charges = await self._optional(self.client.charges(self.vehicle_id, 1), cache.charges)
                cache.charges_at = now
        except VigieAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth") from err
        except VigieRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                retry_after=float(err.retry_after or 60),
            ) from err
        except VigieNotFoundError as err:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="vehicle_not_found") from err
        except VigieForbiddenError as err:
            raise UpdateFailed(translation_domain=DOMAIN, translation_key="read_forbidden") from err
        except VigieError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": err.code or type(err).__name__},
            ) from err

        charges = self._cache.charges or {}
        rows = charges.get("data") or []
        data = VigieData(
            state=state,
            battery=self._cache.battery,
            last_charge=rows[0] if rows else None,
            charges_total=int((charges.get("meta") or {}).get("total") or len(rows)),
        )
        self._watch_options(data.options)
        return data

    async def _optional(self, call: Any, previous: dict[str, Any] | None) -> dict[str, Any] | None:
        """Secondary endpoints: keep the previous value on a transient error."""
        try:
            return await call
        except (VigieAuthError, VigieRateLimitError):
            raise
        except VigieError as err:
            _LOGGER.debug("Vehicle %s: secondary endpoint failed (%s)", self.vehicle_id, err.code)
            return previous

    def _watch_options(self, options: dict[str, bool]) -> None:
        """Controls exist only when the car option is on: reload when options change."""
        if self._initial_options is None:
            self._initial_options = dict(options)
            return
        if options != self._initial_options:
            _LOGGER.info("Vehicle %s: options changed in Vigie, reloading", self.vehicle_id)
            self._initial_options = dict(options)
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
