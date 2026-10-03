"""Dashboard buttons bridge: publication, states, orders and the Pusher WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

from aiohttp import WSMessage, WSMsgType
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.vigie.bridge import DashboardBridge, exposed_entities, pusher_error_delay
from custom_components.vigie.const import CONF_EXPOSED_ENTITIES, CONF_SCAN_INTERVAL, CONF_SIGNAL_BUTTONS, DOMAIN

from .conftest import API, KEY, FakeVigie, make_entry

LIGHT = "light.salon"
SCRIPT = "script.portail"
APP_KEY = "appkey123"
SOCKET = {
    "url": f"wss://ws.vigie.test/app/{APP_KEY}?protocol=7&client=iodek-ha&version=0.5.0",
    "channel": "private-ha.7",
    "auth_endpoint": "/ha/socket-auth",
    "activity_timeout": 20,
}
AUTH = f"{APP_KEY}:0123abcd"


def _publish(vigie: FakeVigie, socket: dict | None = None, status: int = 200, code: str | None = None) -> None:
    body: dict[str, Any] = {"link_id": 7, "socket": socket, "services": {"script": ["turn_on"]}}
    if status != 200:
        body = {"message": "x", "code": code, "ability": "domotique"}
    vigie.mock.put(f"{API}/ha/entities", status=status, json=body)


def _report(vigie: FakeVigie, action_id: int) -> None:
    vigie.mock.post(f"{API}/ha/actions/{action_id}", json={"ok": True})


def _published(vigie: FakeVigie) -> list[dict]:
    return vigie.calls("PUT", "/ha/entities")


def _future(seconds: int = 15) -> str:
    return (dt_util.utcnow() + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _until(cond: Callable[[], bool], timeout: float = 3.0) -> None:
    # Spin first: with freezegun the loop clock is frozen and real sleeps never end.
    for _ in range(100):
        if cond():
            return
        await asyncio.sleep(0)
    async with asyncio.timeout(timeout):
        while not cond():
            await asyncio.sleep(0.01)


async def _spin() -> None:
    for _ in range(50):
        await asyncio.sleep(0)


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Move the clock; async_fire_time_changed also fires the loop timers (asyncio.sleep) that are due."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def _setup(hass: HomeAssistant, entities: list[str] | None = None) -> MockConfigEntry:
    base = make_entry()
    options = dict(base.options)
    if entities is not None:
        options[CONF_EXPOSED_ENTITIES] = entities
    entry = MockConfigEntry(domain=base.domain, title=base.title, unique_id=base.unique_id, data=base.data, options=options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _states(hass: HomeAssistant) -> None:
    hass.states.async_set(LIGHT, "on", {"friendly_name": "Salon"})
    hass.states.async_set(SCRIPT, "off", {"friendly_name": "Ouvrir le portail", "icon": "mdi:gate"})


def test_exposed_entities_filter() -> None:
    options = {CONF_EXPOSED_ENTITIES: [LIGHT, "sensor.temp", "Light.Bad", LIGHT, "lock.porte"]}
    assert exposed_entities(options) == [LIGHT, "lock.porte"]
    assert exposed_entities({}) == []


def test_pusher_error_delay() -> None:
    assert pusher_error_delay(4001) == 60
    assert pusher_error_delay(4100) == 1
    assert pusher_error_delay(4201) == 0
    assert pusher_error_delay(None) is None


async def test_publish_on_start(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie)
    _states(hass)
    hass.states.async_set("switch.prise", "on", {"friendly_name": "Prise", "icon": "hass:power"})
    entry = await _setup(hass, [SCRIPT, LIGHT, "switch.prise", "fan.absent"])
    await _until(lambda: len(_published(vigie)) == 1)
    body = _published(vigie)[0]
    assert body["instance"] == {"name": "test home", "ha_version": HA_VERSION, "integration_version": "0.5.0"}
    assert body["entities"] == [
        {"entity_id": SCRIPT, "name": "Ouvrir le portail", "icon": "mdi:gate", "state": "off"},
        {"entity_id": LIGHT, "name": "Salon", "icon": None, "state": "on"},
        {"entity_id": "switch.prise", "name": "Prise", "icon": None, "state": "on"},
        {"entity_id": "fan.absent", "name": "fan.absent", "icon": None, "state": None},
    ]
    headers = next(h for m, u, _d, h in vigie.mock.mock_calls if str(u).endswith("/ha/entities"))
    assert headers["Authorization"] == f"Bearer {KEY}"
    bridge = entry.runtime_data.bridge
    assert bridge.link_id == 7 and bridge.counters["publications"] == 1


async def test_no_entity_no_bridge(hass: HomeAssistant, vigie: FakeVigie) -> None:
    entry = await _setup(hass, [])
    assert entry.runtime_data.bridge is None
    assert _published(vigie) == []
    assert vigie.calls("POST", "/ha/states") == []


async def test_options_expose_then_clear(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie)
    entry = await _setup(hass)
    assert entry.runtime_data.bridge is None
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 60, CONF_SIGNAL_BUTTONS: False, CONF_EXPOSED_ENTITIES: [LIGHT]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_EXPOSED_ENTITIES] == [LIGHT]
    assert entry.runtime_data.bridge is not None
    await _until(lambda: len(_published(vigie)) == 1)

    # Clearing the list stops the bridge and asks ioDek to remove the buttons.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60, CONF_SIGNAL_BUTTONS: False}
    )
    await hass.async_block_till_done()
    assert CONF_EXPOSED_ENTITIES not in entry.options
    assert entry.runtime_data.bridge is None
    await _until(lambda: len(_published(vigie)) == 2)
    assert _published(vigie)[1]["entities"] == []


async def test_states_grouped(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _publish(vigie)
    vigie.mock.post(f"{API}/ha/states", json={"ok": True, "updated": 2})
    _states(hass)
    entry = await _setup(hass, [LIGHT, SCRIPT])
    await _until(lambda: len(_published(vigie)) == 1)

    hass.states.async_set(LIGHT, "off", {"friendly_name": "Salon"})
    hass.states.async_set(SCRIPT, "on", {"friendly_name": "Ouvrir le portail"})
    hass.states.async_set(LIGHT, "on", {"friendly_name": "Salon", "brightness": 10})
    hass.states.async_set("light.other", "off")
    await hass.async_block_till_done()
    assert vigie.calls("POST", "/ha/states") == []

    freezer.tick(timedelta(seconds=1.1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    sent = vigie.calls("POST", "/ha/states")
    assert sent == [{"states": [{"entity_id": LIGHT, "state": "on"}, {"entity_id": SCRIPT, "state": "on"}]}]
    assert entry.runtime_data.bridge.counters["states_sent"] == 2

    # Attribute-only change: nothing sent.
    hass.states.async_set(LIGHT, "on", {"friendly_name": "Salon", "brightness": 200})
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(vigie.calls("POST", "/ha/states")) == 1


async def test_republish_every_6_hours(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _publish(vigie)
    _states(hass)
    # Keep the "no socket" retry out of the way: only the 6 h timer publishes here.
    with patch("custom_components.vigie.bridge.BRIDGE_NO_SOCKET_RETRY", 10 * 3600):
        await _setup(hass, [LIGHT])
        await _until(lambda: len(_published(vigie)) == 1)
        freezer.tick(timedelta(hours=5, minutes=59))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert len(_published(vigie)) == 1
        freezer.tick(timedelta(minutes=2))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert len(_published(vigie)) == 2


async def test_no_socket_publishes_again(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory) -> None:
    _publish(vigie, socket=None)
    _states(hass)
    await _setup(hass, [LIGHT])
    await _until(lambda: len(_published(vigie)) == 1)
    await _tick(hass, freezer, timedelta(minutes=4))
    await _spin()
    assert len(_published(vigie)) == 1
    await _tick(hass, freezer, timedelta(minutes=1, seconds=1))
    await _until(lambda: len(_published(vigie)) == 2)


async def test_valid_action(hass: HomeAssistant, vigie: FakeVigie, caplog: pytest.LogCaptureFixture) -> None:
    _publish(vigie)
    _report(vigie, 123)
    _states(hass)
    calls = async_mock_service(hass, "light", "toggle")
    caplog.set_level(logging.DEBUG, logger="custom_components.vigie")
    entry = await _setup(hass, [LIGHT, SCRIPT])
    bridge = entry.runtime_data.bridge
    await bridge.async_handle_action({"id": 123, "entity_id": LIGHT, "service": "toggle", "expires_at": _future()})
    assert len(calls) == 1
    assert calls[0].data["entity_id"] in (LIGHT, [LIGHT])
    assert isinstance(calls[0].context, Context)
    assert vigie.calls("POST", "/ha/actions/123") == [{"ok": True}]
    assert bridge.counters["actions_executed"] == 1
    assert bridge.last_action["ok"] is True
    assert "ioDek : toggle sur light.salon" in caplog.text
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    ("order", "error"),
    [
        ({"entity_id": "light.cuisine", "service": "toggle"}, "entity_not_exposed"),
        ({"entity_id": SCRIPT, "service": "turn_off"}, "service_not_allowed"),
        ({"entity_id": LIGHT, "service": "toggle", "expires_at": "2020-01-01T00:00:00Z"}, "expired"),
        ({"entity_id": LIGHT, "service": "toggle", "expires_at": None}, "expired"),
    ],
)
async def test_refused_action(hass: HomeAssistant, vigie: FakeVigie, order: dict, error: str) -> None:
    _publish(vigie)
    _report(vigie, 5)
    _states(hass)
    light_calls = async_mock_service(hass, "light", "toggle")
    script_calls = async_mock_service(hass, "script", "turn_off")
    entry = await _setup(hass, [LIGHT, SCRIPT])
    bridge = entry.runtime_data.bridge
    await bridge.async_handle_action({"id": 5, "expires_at": _future(), **order})
    assert light_calls == [] and script_calls == []
    assert vigie.calls("POST", "/ha/actions/5") == [{"ok": False, "error": error}]
    assert bridge.counters["actions_refused"] == 1


async def test_ha_error_and_timeout(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie)
    _report(vigie, 1)
    _report(vigie, 2)
    _states(hass)

    async def _fail(call: ServiceCall) -> None:
        raise HomeAssistantError("Portail injoignable")

    async def _slow(call: ServiceCall) -> None:
        await asyncio.sleep(1)

    hass.services.async_register("script", "turn_on", _fail)
    hass.services.async_register("light", "toggle", _slow)
    entry = await _setup(hass, [LIGHT, SCRIPT])
    bridge = entry.runtime_data.bridge
    await bridge.async_handle_action({"id": 1, "entity_id": SCRIPT, "service": "turn_on", "expires_at": _future()})
    assert vigie.calls("POST", "/ha/actions/1") == [{"ok": False, "error": "ha_error", "message": "Portail injoignable"}]
    with patch("custom_components.vigie.bridge.BRIDGE_ACTION_TIMEOUT", 0.05):
        await bridge.async_handle_action({"id": 2, "entity_id": LIGHT, "service": "toggle", "expires_at": _future()})
    assert vigie.calls("POST", "/ha/actions/2") == [{"ok": False, "error": "timeout"}]
    assert bridge.counters["actions_failed"] == 2


async def test_duplicate_action(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie)
    _report(vigie, 9)
    _states(hass)
    calls = async_mock_service(hass, "script", "turn_on")
    entry = await _setup(hass, [SCRIPT])
    bridge = entry.runtime_data.bridge
    order = {"id": 9, "entity_id": SCRIPT, "service": "turn_on", "expires_at": _future()}
    await bridge.async_handle_action(order)
    await bridge.async_handle_action(dict(order))
    assert len(calls) == 1
    assert len(vigie.calls("POST", "/ha/actions/9")) == 1


@pytest.mark.parametrize("code", ["ability_missing", "plan_required"])
async def test_refusal_stops_bridge(hass: HomeAssistant, vigie: FakeVigie, freezer: FrozenDateTimeFactory, code: str) -> None:
    _publish(vigie, status=403, code=code)
    _states(hass)
    entry = await _setup(hass, [LIGHT])
    bridge = entry.runtime_data.bridge
    await _until(lambda: bridge.suspended is not None)
    assert bridge.suspended == code
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"bridge_{entry.entry_id}")
    assert issue is not None and issue.translation_key == f"bridge_{code}"

    # Stopped: no state sent, no new publication.
    hass.states.async_set(LIGHT, "off")
    await hass.async_block_till_done()
    freezer.tick(timedelta(hours=7))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(_published(vigie)) == 1
    assert vigie.calls("POST", "/ha/states") == []

    # A new start (options change) lifts the suspension.
    vigie.mock.clear_requests()
    vigie.register(clear=False)
    _publish(vigie)
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_SCAN_INTERVAL: 90})
    await hass.async_block_till_done()
    await _until(lambda: len(_published(vigie)) == 1)
    assert entry.runtime_data.bridge.suspended is None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"bridge_{entry.entry_id}") is None


async def test_unauthorized_starts_reauth(hass: HomeAssistant, vigie: FakeVigie) -> None:
    vigie.mock.put(f"{API}/ha/entities", status=401, json={"message": "x", "code": "api_key_invalid"})
    entry = await _setup(hass, [LIGHT])
    await hass.async_block_till_done()
    await _until(lambda: entry.runtime_data.bridge.last_error == "invalid_auth")
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(f["context"]["source"] == "reauth" for f in flows)


class FakeWS:
    """Minimal Pusher server side of one WebSocket connection."""

    def __init__(self) -> None:
        self.incoming: asyncio.Queue[WSMessage] = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    def push(self, event: str, data: dict[str, Any], channel: str | None = None) -> None:
        message: dict[str, Any] = {"event": event, "data": json.dumps(data)}
        if channel:
            message["channel"] = channel
        self.incoming.put_nowait(WSMessage(WSMsgType.TEXT, json.dumps(message), None))

    async def receive(self) -> WSMessage:
        return await self.incoming.get()

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.incoming.put_nowait(WSMessage(WSMsgType.CLOSED, None, None))

    def events(self) -> list[str]:
        return [m["event"] for m in self.sent]


async def test_websocket_protocol(
    hass: HomeAssistant, hass_client: ClientSessionGenerator, vigie: FakeVigie, caplog: pytest.LogCaptureFixture
) -> None:
    _publish(vigie, socket=SOCKET)
    vigie.mock.post(f"{API}/ha/socket-auth", json={"auth": AUTH})
    _report(vigie, 123)
    _states(hass)
    calls = async_mock_service(hass, "script", "turn_on")
    caplog.set_level(logging.DEBUG, logger="custom_components.vigie")
    ws = FakeWS()
    connect = AsyncMock(return_value=ws)
    with patch.object(DashboardBridge, "_ws_connect", connect):
        entry = await _setup(hass, [SCRIPT])
        bridge = entry.runtime_data.bridge
        await _until(lambda: connect.await_count == 1)
        assert connect.await_args.args[0] == SOCKET["url"]

        ws.push("pusher:connection_established", {"socket_id": "123.456", "activity_timeout": 20})
        await _until(lambda: "pusher:subscribe" in ws.events())
        assert vigie.calls("POST", "/ha/socket-auth") == [{"socket_id": "123.456", "channel_name": "private-ha.7"}]
        assert ws.sent[-1] == {"event": "pusher:subscribe", "data": {"channel": "private-ha.7", "auth": AUTH}}

        ws.push("pusher_internal:subscription_succeeded", {}, channel="private-ha.7")
        await _until(lambda: bridge.connected)

        ws.push("pusher:ping", {})
        await _until(lambda: "pusher:pong" in ws.events())
        assert ws.sent[-1] == {"event": "pusher:pong", "data": {}}

        # An order on another channel is ignored.
        ws.push("action", {"id": 99, "entity_id": SCRIPT, "service": "turn_on", "expires_at": _future()}, "private-ha.8")
        ws.push("action", {"id": 123, "entity_id": SCRIPT, "service": "turn_on", "expires_at": _future()}, "private-ha.7")
        await _until(lambda: len(vigie.calls("POST", "/ha/actions/123")) == 1)
        assert len(calls) == 1
        assert vigie.calls("POST", "/ha/actions/123") == [{"ok": True}]
        assert vigie.calls("POST", "/ha/actions/99") == []

        diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
        text = json.dumps(diag)
        assert diag["bridge"]["connected"] is True
        assert diag["bridge"]["socket"]["host"] == "ws.vigie.test"
        assert diag["bridge"]["last_action"]["id"] == 123
        assert APP_KEY not in text and KEY not in text
        assert APP_KEY not in caplog.text and KEY not in caplog.text

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert ws.closed


async def test_websocket_ping_and_reconnect(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie, socket=SOCKET)
    vigie.mock.post(f"{API}/ha/socket-auth", json={"auth": AUTH})
    sockets = [FakeWS(), FakeWS(), FakeWS()]
    connect = AsyncMock(side_effect=sockets)
    with (
        patch.object(DashboardBridge, "_ws_connect", connect),
        patch("custom_components.vigie.bridge.BRIDGE_PONG_TIMEOUT", 0.05),
        patch("custom_components.vigie.bridge.BRIDGE_RECONNECT_DELAYS", (0, 0)),
    ):
        entry = await _setup(hass, [LIGHT])
        bridge = entry.runtime_data.bridge
        first = sockets[0]
        await _until(lambda: connect.await_count == 1)
        # Silence longer than the activity timeout: the client pings, then reconnects without pong.
        first.push("pusher:connection_established", {"socket_id": "1.1", "activity_timeout": 0.05})
        await _until(lambda: "pusher:ping" in first.events())
        await _until(lambda: connect.await_count == 2)
        assert first.closed
        # Each reconnection publishes the list again.
        assert len(_published(vigie)) == 2

        # pusher:error 4200: reconnect at once.
        second = sockets[1]
        second.push("pusher:error", {"code": 4200, "message": "Generic reconnect"})
        await _until(lambda: connect.await_count == 3)
        assert bridge.counters["reconnections"] == 2
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_no_socket_no_websocket(hass: HomeAssistant, vigie: FakeVigie) -> None:
    _publish(vigie, socket=None)
    connect = AsyncMock()
    with patch.object(DashboardBridge, "_ws_connect", connect):
        entry = await _setup(hass, [LIGHT])
        await _until(lambda: len(_published(vigie)) == 1)
        await asyncio.sleep(0.05)
        assert connect.await_count == 0
        assert entry.runtime_data.bridge.connected is False
