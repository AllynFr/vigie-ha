"""Shared fixtures: a fake Vigie API served through aioclient_mock."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.vigie.const import (
    CONF_ABILITIES,
    CONF_SCAN_INTERVAL,
    CONF_SIGNAL_BUTTONS,
    CONF_VEHICLES,
    DOMAIN,
)

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://vigie.test"
API = f"{URL}/api/v1"
KEY = "2|vigie_secretsecretsecret"


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test."""


class FakeVigie:
    """Registers the read endpoints; tests tweak the payloads before setup."""

    def __init__(self, mock: AiohttpClientMocker) -> None:
        self.mock = mock
        self.vehicles = load("vehicles.json")
        self.state = load("state.json")
        self.battery = load("battery.json")
        self.charges = load("charges.json")

    def register(self, clear: bool = True) -> None:
        """Default read endpoints. Mocks registered before these take precedence."""
        if clear:
            self.mock.clear_requests()
        self.mock.get(f"{API}/vehicles", json=self.vehicles)
        self.mock.get(f"{API}/vehicles/1/state", json=self.state)
        self.mock.get(f"{API}/vehicles/1/battery", json=self.battery)
        self.mock.get(f"{API}/vehicles/1/charges", json=self.charges)

    def set_options(self, **options: bool) -> None:
        for target in (self.state["options"], self.vehicles["data"][0]["options"]):
            target.update(options)

    def calls(self, method: str, path: str) -> list[Any]:
        """(method, url, body) of recorded requests to an API path."""
        out = []
        for m, url, data, _headers in self.mock.mock_calls:
            if m.upper() == method and str(url).split("?")[0] == f"{API}{path}":
                out.append(data)
        return out


@pytest.fixture
def vigie(aioclient_mock: AiohttpClientMocker) -> FakeVigie:
    fake = FakeVigie(aioclient_mock)
    fake.register()
    return fake


def make_entry(abilities: list[str] | None = None, signal_buttons: bool = False) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Tessy",
        unique_id="vigie.test:1",
        data={
            "url": URL,
            "api_key": KEY,
            CONF_VEHICLES: [1],
            CONF_ABILITIES: abilities if abilities is not None else ["lecture"],
        },
        options={CONF_SCAN_INTERVAL: 60, CONF_SIGNAL_BUTTONS: signal_buttons},
    )


def deep(obj: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(obj)
