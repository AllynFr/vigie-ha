"""Send the user's position (a person or device_tracker entity) to ioDek.

ioDek uses it for the "away" mode of scheduled climate: the schedule does not
run when the user is far from the car. The server keeps one position per user,
considers a Home Assistant position fresh for 6 h and forgets it after 24 h.

Coordinates are never logged.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_GPS_ACCURACY, ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .api import VigieClient, VigieCommandError, VigieError, VigieForbiddenError
from .const import DOMAIN, LOCATION_MIN_INTERVAL, LOCATION_MIN_MOVE_M, LOCATION_REFRESH, LOCATION_SOURCE

_LOGGER = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_008.8

# Server answers that stop the sending until the options change or HA restarts.
SUSPEND_ABILITY = "ability_missing"
SUSPEND_DISABLED = "location_disabled"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def position_from_state(state: State | None) -> dict[str, Any] | None:
    """Payload for POST /me/location, or None when the state has no usable coordinates."""
    if state is None:
        return None
    lat = _number(state.attributes.get(ATTR_LATITUDE))
    lon = _number(state.attributes.get(ATTR_LONGITUDE))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    payload: dict[str, Any] = {"latitude": lat, "longitude": lon}
    accuracy = _number(state.attributes.get(ATTR_GPS_ACCURACY))
    if accuracy is not None and accuracy >= 0:
        payload["accuracy_m"] = round(accuracy)
    payload["at"] = state.last_updated.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["source"] = LOCATION_SOURCE
    return payload


class LocationReporter:
    """Follows one entity and sends its position to ioDek when it matters."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: VigieClient, entity_id: str) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.entity_id = entity_id
        self.suspended: str | None = None
        self.last_error: str | None = None
        self.last_sent: dict[str, Any] | None = None
        self.last_sent_at: datetime | None = None
        self.sent_count = 0
        self._last_attempt: datetime | None = None
        self._retry = False
        self._pending_force = False
        self._unsub_state: CALLBACK_TYPE | None = None
        self._unsub_pending: CALLBACK_TYPE | None = None
        self._unsub_refresh: CALLBACK_TYPE | None = None

    @property
    def issue_id(self) -> str:
        return f"location_{self.entry.entry_id}"

    @callback
    def async_start(self) -> None:
        # A new start (setup, reload after an options change) lifts a suspension.
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
        self._unsub_state = async_track_state_change_event(self.hass, [self.entity_id], self._state_changed)
        self._evaluate()

    @callback
    def async_stop(self) -> None:
        for name in ("_unsub_state", "_unsub_pending", "_unsub_refresh"):
            unsub = getattr(self, name)
            if unsub is not None:
                unsub()
                setattr(self, name, None)
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)

    @callback
    def _state_changed(self, event: Event[EventStateChangedData]) -> None:
        self._evaluate()

    @callback
    def _evaluate(self, force: bool = False) -> None:
        """Send the current position if it is new, far enough, or due for a refresh."""
        if self.suspended:
            return
        payload = position_from_state(self.hass.states.get(self.entity_id))
        if payload is None:
            return
        if not force and not self._retry and self.last_sent is not None:
            moved = haversine_m(
                self.last_sent["latitude"], self.last_sent["longitude"], payload["latitude"], payload["longitude"]
            )
            if moved <= LOCATION_MIN_MOVE_M:
                return
        now = dt_util.utcnow()
        if self._last_attempt is not None and now - self._last_attempt < LOCATION_MIN_INTERVAL:
            # Too early: send the latest position at the end of the minute.
            self._pending_force |= force
            if self._unsub_pending is None:
                delay = (self._last_attempt + LOCATION_MIN_INTERVAL - now).total_seconds()
                self._unsub_pending = async_call_later(self.hass, delay, self._pending_due)
            return
        self._last_attempt = now
        if self._unsub_pending is not None:
            self._unsub_pending()
            self._unsub_pending = None
        self._pending_force = False
        self._schedule_refresh()
        self.entry.async_create_task(self.hass, self._send(payload), "vigie_send_location")

    @callback
    def _pending_due(self, _now: datetime) -> None:
        self._unsub_pending = None
        force, self._pending_force = self._pending_force, False
        self._evaluate(force)

    @callback
    def _refresh_due(self, _now: datetime) -> None:
        self._unsub_refresh = None
        self._evaluate(force=True)

    @callback
    def _schedule_refresh(self) -> None:
        if self._unsub_refresh is not None:
            self._unsub_refresh()
        self._unsub_refresh = async_call_later(self.hass, LOCATION_REFRESH.total_seconds(), self._refresh_due)

    async def _send(self, payload: dict[str, Any]) -> None:
        try:
            await self.client.send_location(payload)
        except VigieForbiddenError as err:
            self._suspend(err.code or SUSPEND_ABILITY)
        except VigieCommandError as err:
            if err.status == 409 and err.code == SUSPEND_DISABLED:
                self._suspend(SUSPEND_DISABLED)
            else:
                self._failed(err)
        except VigieError as err:  # 429, 422, network: retried later
            self._failed(err)
        else:
            self.last_sent = payload
            self.last_sent_at = dt_util.utcnow()
            self.last_error = None
            self._retry = False
            self.sent_count += 1

    @callback
    def _failed(self, err: VigieError) -> None:
        # Retried on the next change or the next refresh, never in a loop.
        self.last_error = err.code or type(err).__name__
        self._retry = True
        _LOGGER.debug("ioDek did not record the position (%s), will retry later", self.last_error)

    @callback
    def _suspend(self, code: str) -> None:
        self.suspended = code
        self.last_error = code
        for name in ("_unsub_pending", "_unsub_refresh"):
            unsub = getattr(self, name)
            if unsub is not None:
                unsub()
                setattr(self, name, None)
        disabled = code == SUSPEND_DISABLED
        _LOGGER.warning(
            "ioDek refused the position of %s (%s): sending stopped until the options change or Home Assistant restarts",
            self.entity_id,
            code,
        )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="location_disabled" if disabled else "location_ability_missing",
            translation_placeholders={"entity": self.entity_id},
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "suspended": self.suspended,
            "last_error": self.last_error,
            "sent_count": self.sent_count,
            "last_sent_at": self.last_sent_at.isoformat() if self.last_sent_at else None,
            "last_sent": dict(self.last_sent) if self.last_sent else None,
        }
