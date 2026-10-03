"""Dashboard buttons: ioDek dashboard buttons act on chosen Home Assistant entities.

ioDek holds no Home Assistant token. The integration publishes the entities the
user picked in the options (PUT /ha/entities), sends their state changes
(POST /ha/states) and listens for orders on a Pusher WebSocket (Laravel Reverb)
that Home Assistant opens itself: nothing has to be reachable from the Internet.
An order is run only for an exposed entity and a service of the closed list,
then reported back (POST /ha/actions/{id}).

The same channel carries the car events (`iodek.event`: charge started, alarm...),
fired in Home Assistant as `vigie_event` with the car's device_id. With no exposed
entity, the bridge still runs for these events when the key has the home
automation permission.

Neither the API key nor the socket URL (which holds the app key) is ever logged.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
import json
import logging
import re
from typing import Any
from urllib.parse import urlsplit

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_ICON, __version__ as HA_VERSION
from homeassistant.core import CALLBACK_TYPE, Context, Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .api import REQUEST_TIMEOUT, VigieAuthError, VigieClient, VigieError, VigieForbiddenError, VigieRateLimitError
from .const import (
    BRIDGE_ACTION_TIMEOUT,
    BRIDGE_ACTIVITY_TIMEOUT,
    BRIDGE_EVENT,
    BRIDGE_MAX_ENTITIES,
    BRIDGE_MESSAGE_MAX,
    BRIDGE_NAME_MAX,
    BRIDGE_NO_SOCKET_RETRY,
    BRIDGE_PONG_TIMEOUT,
    BRIDGE_PUBLISH_RETRY_DELAYS,
    BRIDGE_RECONNECT_DELAYS,
    BRIDGE_REPUBLISH,
    BRIDGE_SEEN_ACTIONS,
    BRIDGE_SERVICES,
    BRIDGE_STABLE_AFTER,
    BRIDGE_STATE_MAX,
    BRIDGE_STATES_DELAY,
    CONF_EXPOSED_ENTITIES,
    DOMAIN,
    EVENT_FIELDS,
    EVENT_REFRESH_TYPES,
    EVENT_VIGIE,
)
from .entity import vehicle_identifier

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
ICON_RE = re.compile(r"^mdi:[a-z0-9-]+$")

# 403 answers to the publication that stop the bridge until the next start.
SUSPEND_CODES = ("ability_missing", "plan_required")

# Refusals reported to ioDek (POST /ha/actions/{id}).
ERROR_EXPIRED = "expired"
ERROR_NOT_EXPOSED = "entity_not_exposed"
ERROR_SERVICE = "service_not_allowed"
ERROR_TIMEOUT = "timeout"
ERROR_HA = "ha_error"

WS_ENDED = (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR)


def exposed_entities(options: Mapping[str, Any]) -> list[str]:
    """Entity ids of the options the bridge may expose: valid id, allowed domain, at most 100."""
    out: list[str] = []
    for value in options.get(CONF_EXPOSED_ENTITIES) or []:
        entity_id = str(value)
        if ENTITY_ID_RE.match(entity_id) and entity_id.split(".", 1)[0] in BRIDGE_SERVICES and entity_id not in out:
            out.append(entity_id)
    return out[:BRIDGE_MAX_ENTITIES]


def _clip(value: Any, size: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:size] if text else None


def _positive(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def state_value(state: State | None) -> str | None:
    return _clip(state.state, BRIDGE_STATE_MAX) if state is not None else None


def entity_payload(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """One item of PUT /ha/entities."""
    state = hass.states.get(entity_id)
    attributes = state.attributes if state is not None else {}
    icon = attributes.get(ATTR_ICON)
    return {
        "entity_id": entity_id,
        "name": _clip(attributes.get(ATTR_FRIENDLY_NAME), BRIDGE_NAME_MAX) or entity_id[:BRIDGE_NAME_MAX],
        "icon": icon if isinstance(icon, str) and ICON_RE.match(icon) else None,
        "state": state_value(state),
    }


async def instance_payload(hass: HomeAssistant) -> dict[str, Any]:
    integration = await async_get_integration(hass, DOMAIN)
    return {
        "name": _clip(hass.config.location_name, BRIDGE_NAME_MAX) or "Home Assistant",
        "ha_version": HA_VERSION,
        "integration_version": str(integration.version or ""),
    }


async def async_withdraw(hass: HomeAssistant, client: VigieClient) -> None:
    """Publish an empty list so that ioDek removes the buttons (entities cleared in the options)."""
    try:
        await client.publish_entities({"instance": await instance_payload(hass), "entities": []})
    except VigieError as err:
        _LOGGER.debug("ioDek did not take the empty entity list (%s)", err.code or type(err).__name__)


def socket_config(raw: Any) -> dict[str, Any] | None:
    """Usable `socket` block of the publication answer, or None (no real-time channel)."""
    if not isinstance(raw, dict):
        return None
    url, channel = raw.get("url"), raw.get("channel")
    if not isinstance(url, str) or urlsplit(url).scheme not in ("wss", "ws"):
        return None
    if not isinstance(channel, str) or not channel:
        return None
    return {
        "url": url,
        "channel": channel,
        "activity_timeout": _positive(raw.get("activity_timeout")) or BRIDGE_ACTIVITY_TIMEOUT,
    }


def pusher_error_delay(code: Any) -> float | None:
    """Delay asked by a pusher:error code; None means the growing delays."""
    if not isinstance(code, int) or isinstance(code, bool):
        return None
    if 4000 <= code < 4100:
        # Do not reconnect as is: wait the longest delay (a new publication comes first).
        return BRIDGE_RECONNECT_DELAYS[-1]
    if 4100 <= code < 4200:
        return 1
    if 4200 <= code < 4300:
        return 0
    return None


def _parse_message(text: str) -> tuple[str | None, dict[str, Any], str | None]:
    """(event, data, channel) of a Pusher message; `data` is often a JSON string."""
    try:
        message = json.loads(text)
    except ValueError:
        return None, {}, None
    if not isinstance(message, dict) or not isinstance(message.get("event"), str):
        return None, {}, None
    data = message.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    channel = message.get("channel")
    return message["event"], data if isinstance(data, dict) else {}, channel if isinstance(channel, str) else None


class _Stop(Exception):
    """The bridge must stop (suspended, reauthentication, unload)."""


class _Reconnect(Exception):
    """End of one WebSocket session."""

    def __init__(self, reason: str, delay: float | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.delay = delay


class DashboardBridge:
    """Publishes the exposed entities to ioDek and runs the orders of its dashboard buttons."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: VigieClient, entity_ids: Iterable[str]) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.entities = list(entity_ids)
        self.suspended: str | None = None
        self.last_error: str | None = None
        self.connected = False
        self.link_id: Any = None
        self.last_published_at: datetime | None = None
        self.last_action: dict[str, Any] | None = None
        self.last_event: dict[str, Any] | None = None
        self.counters = {
            "publications": 0,
            "states_sent": 0,
            "actions_executed": 0,
            "actions_refused": 0,
            "actions_failed": 0,
            "events_fired": 0,
            "reconnections": 0,
        }
        self._socket: dict[str, Any] | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None
        self._instance: dict[str, Any] | None = None
        self._seen: deque[int] = deque(maxlen=BRIDGE_SEEN_ACTIONS)
        self._pending: dict[str, str | None] = {}
        self._failures = 0
        self._publish_failures = 0
        self._connected_at: float | None = None
        self._stopped = False
        self._unsub_state: CALLBACK_TYPE | None = None
        self._unsub_flush: CALLBACK_TYPE | None = None
        self._unsub_refresh: CALLBACK_TYPE | None = None

    @property
    def issue_id(self) -> str:
        return f"bridge_{self.entry.entry_id}"

    # Lifecycle

    @callback
    def async_start(self) -> None:
        # A new start (setup, reload after an options change) lifts a suspension.
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
        self._unsub_state = async_track_state_change_event(self.hass, self.entities, self._state_changed)
        self._unsub_refresh = async_track_time_interval(self.hass, self._refresh_due, BRIDGE_REPUBLISH)
        self._task = self.entry.async_create_background_task(self.hass, self._run(), "vigie_dashboard_bridge")

    @callback
    def async_stop(self) -> None:
        self._stopped = True
        self._halt()
        ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)

    @callback
    def _halt(self) -> None:
        for name in ("_unsub_state", "_unsub_flush", "_unsub_refresh"):
            unsub = getattr(self, name)
            if unsub is not None:
                unsub()
                setattr(self, name, None)
        self._pending.clear()
        self.connected = False
        task, self._task = self._task, None
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()

    @callback
    def _suspend(self, code: str) -> None:
        self.suspended = code
        self.last_error = code
        self._stopped = True
        self._halt()
        if not self.entities:
            # Events only, no button exposed: nothing for the user to repair.
            _LOGGER.debug("ioDek refused the events channel (%s)", code)
            return
        _LOGGER.warning(
            "ioDek refused the dashboard buttons (%s): bridge stopped until the options change or Home Assistant restarts",
            code,
        )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=f"bridge_{code}",
        )

    @callback
    def _reauth(self) -> None:
        # The reauthentication reloads the entry, which starts a new bridge.
        self.last_error = "invalid_auth"
        self._stopped = True
        self._halt()
        self.entry.async_start_reauth(self.hass)

    # Publication

    async def _run(self) -> None:
        """Publish, then keep the WebSocket open; publish again before each reconnection."""
        while not self._stopped:
            try:
                body = await self._publish()
            except _Stop:
                return
            except VigieError as err:
                await asyncio.sleep(self._publish_retry_delay(err))
                continue
            socket = socket_config(body.get("socket"))
            if socket is None:
                _LOGGER.debug("ioDek has no real-time channel for now, publishing again in %s s", BRIDGE_NO_SOCKET_RETRY)
                await asyncio.sleep(BRIDGE_NO_SOCKET_RETRY)
                continue
            delay = await self._session(socket)
            if delay is None:
                return
            self.counters["reconnections"] += 1
            await asyncio.sleep(delay)

    async def _publish(self) -> dict[str, Any]:
        """PUT /ha/entities. Raises _Stop when the bridge must stop, VigieError to retry later."""
        if self._stopped:
            raise _Stop
        if self._instance is None:
            self._instance = await instance_payload(self.hass)
        payload = {
            "instance": self._instance,
            "entities": [entity_payload(self.hass, entity_id) for entity_id in self.entities],
        }
        try:
            body = await self.client.publish_entities(payload)
        except VigieAuthError:
            self._reauth()
            raise _Stop from None
        except VigieForbiddenError as err:
            if err.code in SUSPEND_CODES:
                self._suspend(err.code)
                raise _Stop from None
            self._failed(err)
            raise
        except VigieError as err:
            self._failed(err)
            raise
        if self._stopped:
            raise _Stop
        body = body if isinstance(body, dict) else {}
        self.link_id = body.get("link_id")
        self.last_published_at = dt_util.utcnow()
        self.last_error = None
        self._publish_failures = 0
        self.counters["publications"] += 1
        return body

    def _publish_retry_delay(self, err: VigieError) -> float:
        delay = BRIDGE_PUBLISH_RETRY_DELAYS[min(self._publish_failures, len(BRIDGE_PUBLISH_RETRY_DELAYS) - 1)]
        self._publish_failures += 1
        if isinstance(err, VigieRateLimitError) and err.retry_after:
            delay = max(delay, err.retry_after)
        _LOGGER.debug("ioDek did not take the entity list (%s), new try in %s s", self.last_error, delay)
        return delay

    @callback
    def _failed(self, err: VigieError) -> None:
        self.last_error = err.code or type(err).__name__

    @callback
    def _refresh_due(self, _now: datetime) -> None:
        self.entry.async_create_task(self.hass, self._republish(), "vigie_republish_entities")

    async def _republish(self) -> None:
        """Periodic publication. A new channel in the answer closes the socket: the run loop reconnects."""
        try:
            body = await self._publish()
        except (_Stop, VigieError):
            return
        socket = socket_config(body.get("socket"))
        ws = self._ws
        if ws is not None and self._socket is not None and socket != self._socket:
            await ws.close()

    # State changes

    @callback
    def _state_changed(self, event: Event[EventStateChangedData]) -> None:
        old, new = event.data["old_state"], event.data["new_state"]
        if old is not None and new is not None and old.state == new.state:
            return  # attributes only
        self._pending[event.data["entity_id"]] = state_value(new)
        if self._unsub_flush is None:
            self._unsub_flush = async_call_later(self.hass, BRIDGE_STATES_DELAY, self._flush)

    @callback
    def _flush(self, _now: datetime) -> None:
        self._unsub_flush = None
        states = [{"entity_id": entity_id, "state": state} for entity_id, state in self._pending.items()]
        self._pending.clear()
        # Before the first publication, the list itself carries the states.
        if states and self.last_published_at is not None and not self._stopped:
            self.entry.async_create_task(self.hass, self._send_states(states[:BRIDGE_MAX_ENTITIES]), "vigie_send_states")

    async def _send_states(self, states: list[dict[str, Any]]) -> None:
        try:
            await self.client.send_states(states)
        except VigieAuthError:
            self._reauth()
        except VigieError as err:
            # Not retried: the next publication (6 h, reconnection) sends every state again.
            self._failed(err)
            _LOGGER.debug("ioDek did not take the state changes (%s)", self.last_error)
        else:
            self.counters["states_sent"] += len(states)

    # WebSocket (Pusher protocol 7)

    async def _ws_connect(self, url: str) -> aiohttp.ClientWebSocketResponse:
        session = async_get_clientsession(self.hass)
        async with asyncio.timeout(REQUEST_TIMEOUT):
            # No WebSocket heartbeat: Pusher has its own ping/pong.
            return await session.ws_connect(url, heartbeat=None)

    async def _session(self, socket: dict[str, Any]) -> float | None:
        """One WebSocket connection. Returns the delay before the next one, None to stop."""
        self._socket = socket
        self._connected_at = None
        try:
            ws = await self._ws_connect(socket["url"])
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            return self._lost(type(err).__name__, None)
        self._ws = ws
        try:
            await self._listen(ws, socket)
        except _Reconnect as err:
            reason, delay = err.reason, err.delay
        except _Stop:
            return None
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            reason, delay = type(err).__name__, None
        else:
            reason, delay = "closed", None
        finally:
            self._ws = None
            self.connected = False
            if not ws.closed:
                await ws.close()
        return self._lost(reason, delay)

    def _lost(self, reason: str, delay: float | None) -> float | None:
        if self._stopped:
            return None
        loop_time = asyncio.get_running_loop().time()
        if self._connected_at is not None and loop_time - self._connected_at >= BRIDGE_STABLE_AFTER:
            self._failures = 0
        backoff = BRIDGE_RECONNECT_DELAYS[min(self._failures, len(BRIDGE_RECONNECT_DELAYS) - 1)]
        self._failures += 1
        self.last_error = reason
        # The delay asked by the server, but never a tight loop after repeated failures.
        wait = backoff if delay is None else (delay if self._failures == 1 else max(delay, backoff))
        _LOGGER.debug("ioDek dashboard channel lost (%s), reconnecting in %s s", reason, wait)
        return wait

    async def _listen(self, ws: aiohttp.ClientWebSocketResponse, socket: dict[str, Any]) -> None:
        channel: str = socket["channel"]
        activity: float = socket["activity_timeout"]
        waiting_pong = False
        while True:
            try:
                async with asyncio.timeout(BRIDGE_PONG_TIMEOUT if waiting_pong else activity):
                    msg = await ws.receive()
            except TimeoutError:
                if waiting_pong:
                    raise _Reconnect("pong_timeout") from None
                await ws.send_json({"event": "pusher:ping", "data": {}})
                waiting_pong = True
                continue
            if msg.type in WS_ENDED:
                raise _Reconnect("closed")
            # Any message proves the connection is alive.
            waiting_pong = False
            if msg.type is not aiohttp.WSMsgType.TEXT:
                continue
            event, data, msg_channel = _parse_message(msg.data)
            if event == "pusher:connection_established":
                socket_id = data.get("socket_id")
                if not isinstance(socket_id, str) or not socket_id:
                    raise _Reconnect("bad_handshake")
                if (server_timeout := _positive(data.get("activity_timeout"))) is not None:
                    activity = min(activity, server_timeout)
                auth = await self._socket_auth(socket_id, channel)
                await ws.send_json({"event": "pusher:subscribe", "data": {"channel": channel, "auth": auth}})
            elif event == "pusher_internal:subscription_succeeded" and msg_channel == channel:
                self.connected = True
                self._connected_at = asyncio.get_running_loop().time()
                _LOGGER.debug("ioDek dashboard channel connected")
            elif event == "pusher:subscription_error":
                raise _Reconnect("subscription_error")
            elif event == "pusher:ping":
                await ws.send_json({"event": "pusher:pong", "data": {}})
            elif event == "pusher:error":
                code = data.get("code")
                raise _Reconnect(f"pusher_{code}", pusher_error_delay(code))
            elif event == "action" and msg_channel == channel:
                # Run aside so that pings keep flowing during a slow service.
                self.entry.async_create_background_task(self.hass, self.async_handle_action(data), "vigie_dashboard_action")
            elif event == BRIDGE_EVENT and msg_channel == channel:
                self.async_fire_event(data)

    async def _socket_auth(self, socket_id: str, channel: str) -> str:
        try:
            body = await self.client.socket_auth(socket_id, channel)
        except VigieAuthError:
            self._reauth()
            raise _Stop from None
        except VigieError as err:
            raise _Reconnect(f"socket_auth_{err.code or type(err).__name__}") from err
        auth = body.get("auth") if isinstance(body, dict) else None
        if not isinstance(auth, str) or not auth:
            raise _Reconnect("socket_auth_invalid")
        return auth

    # Orders

    def _default_service(self, entity_id: str) -> str:
        domain = entity_id.split(".", 1)[0]
        if domain == "lock":
            state = self.hass.states.get(entity_id)
            return "unlock" if state is not None and state.state == "locked" else "lock"
        return BRIDGE_SERVICES[domain][0]

    async def async_handle_action(self, data: Mapping[str, Any]) -> None:
        """Check one order, run it if allowed, then report the outcome to ioDek."""
        try:
            action_id = int(data["id"])
        except (KeyError, TypeError, ValueError):
            _LOGGER.debug("ioDek order without id ignored")
            return
        if action_id in self._seen:
            _LOGGER.debug("ioDek order %s already handled", action_id)
            return
        self._seen.append(action_id)
        entity_id = str(data.get("entity_id") or "")
        service = str(data.get("service") or "")
        domain = entity_id.split(".", 1)[0]
        error: str | None = None
        message: str | None = None

        expires = dt_util.parse_datetime(str(data.get("expires_at") or ""))
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        # Fail closed: an order without a valid deadline is treated as expired.
        if expires is None or expires <= dt_util.utcnow():
            error = ERROR_EXPIRED
        elif entity_id not in self.entities:
            error = ERROR_NOT_EXPOSED
        else:
            service = service or self._default_service(entity_id)
            if service not in BRIDGE_SERVICES.get(domain, ()):
                error = ERROR_SERVICE

        if error is not None:
            self.counters["actions_refused"] += 1
            _LOGGER.debug("ioDek order %s refused (%s)", action_id, error)
        else:
            _LOGGER.info("ioDek : %s sur %s", service, entity_id)
            try:
                async with asyncio.timeout(BRIDGE_ACTION_TIMEOUT):
                    await self.hass.services.async_call(
                        domain, service, {"entity_id": entity_id}, blocking=True, context=Context()
                    )
            except TimeoutError:
                error = ERROR_TIMEOUT
            except Exception as err:  # any failure of the service is reported, never raised
                error = ERROR_HA
                message = _clip(str(err) or type(err).__name__, BRIDGE_MESSAGE_MAX)
            if error is None:
                self.counters["actions_executed"] += 1
            else:
                self.counters["actions_failed"] += 1
                _LOGGER.debug("ioDek order %s failed (%s)", action_id, error)

        self.last_action = {
            "id": action_id,
            "entity_id": entity_id,
            "service": service,
            "ok": error is None,
            "error": error,
            "at": dt_util.utcnow().isoformat(),
        }
        try:
            await self.client.report_action(action_id, error is None, error, message)
        except VigieAuthError:
            self._reauth()
        except VigieError as err:
            # 409 already_reported, 404 not ours: nothing to do.
            _LOGGER.debug("ioDek did not take the report of order %s (%s)", action_id, err.code or type(err).__name__)

    # Car events

    @callback
    def async_fire_event(self, data: Mapping[str, Any]) -> bool:
        """Fire `vigie_event` for an event of a car of this entry, with the car's device_id."""
        event_type = data.get("type")
        try:
            vehicle_id = int(data["vehicle_id"])
        except (KeyError, TypeError, ValueError):
            vehicle_id = None
        coordinators = getattr(self.entry.runtime_data, "coordinators", {})
        if not isinstance(event_type, str) or not event_type or vehicle_id not in coordinators:
            _LOGGER.debug("ioDek event ignored (type %s, car %s)", event_type, vehicle_id)
            return False
        payload = {key: data[key] for key in EVENT_FIELDS if key in data}
        device = dr.async_get(self.hass).async_get_device(
            identifiers={(DOMAIN, vehicle_identifier(self.client.base_url, vehicle_id))}
        )
        payload["device_id"] = device.id if device else None
        payload["config_entry_id"] = self.entry.entry_id
        self.hass.bus.async_fire(EVENT_VIGIE, payload)
        self.counters["events_fired"] += 1
        self.last_event = {"type": event_type, "vehicle_id": vehicle_id, "at": data.get("at")}
        if event_type in EVENT_REFRESH_TYPES:
            coordinator = coordinators[vehicle_id]
            self.entry.async_create_background_task(
                self.hass, coordinator.async_refresh_after_event(), "vigie_refresh_after_event"
            )
        return True

    def diagnostics(self) -> dict[str, Any]:
        socket = self._socket
        return {
            "entities": list(self.entities),
            "connected": self.connected,
            "suspended": self.suspended,
            "last_error": self.last_error,
            "link_id": self.link_id,
            # Host only: the path of the socket URL holds the app key.
            "socket": (
                {
                    "host": urlsplit(socket["url"]).hostname,
                    "channel": socket["channel"],
                    "activity_timeout": socket["activity_timeout"],
                }
                if socket
                else None
            ),
            "last_published_at": self.last_published_at.isoformat() if self.last_published_at else None,
            "last_action": dict(self.last_action) if self.last_action else None,
            "last_event": dict(self.last_event) if self.last_event else None,
            "counters": dict(self.counters),
        }
