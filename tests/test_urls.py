"""Addresses: default API host, accepted forms of the URL, web app link."""

from __future__ import annotations

from custom_components.vigie.api import app_url, normalize_url
from custom_components.vigie.const import DEFAULT_URL


def test_default_is_the_api_host() -> None:
    assert DEFAULT_URL == "https://api.iodek.fr"


def test_normalize_url() -> None:
    assert normalize_url("https://api.iodek.fr/") == "https://api.iodek.fr"
    assert normalize_url("https://api.iodek.fr/v1") == "https://api.iodek.fr"
    assert normalize_url("https://api.iodek.fr/api/v1/") == "https://api.iodek.fr"
    # Former address, still accepted by the server.
    assert normalize_url("https://vigie.allyn.fr/api/v1") == "https://vigie.allyn.fr"
    # /v1 is only stripped on an api. host.
    assert normalize_url("https://example.org/v1") == "https://example.org/v1"


def test_app_url() -> None:
    assert app_url("https://api.iodek.fr") == "https://iodek.fr"
    assert app_url("https://vigie.allyn.fr") == "https://vigie.allyn.fr"
