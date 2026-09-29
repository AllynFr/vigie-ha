"""Diagnostics must not leak the key, the VIN or any position."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from .conftest import KEY, FakeVigie, make_entry


async def test_diagnostics_redacted(hass: HomeAssistant, hass_client: ClientSessionGenerator, vigie: FakeVigie) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = json.dumps(diag, ensure_ascii=False)

    assert KEY not in text and "vigie_" not in text
    assert "1234" not in text  # masked VIN tail
    assert "48.8584" not in text and "2.2945" not in text
    assert diag["entry"]["data"]["api_key"] == "**REDACTED**"
    vehicle = diag["vehicles"][0]
    assert vehicle["state"]["values"]["Location"] == "**REDACTED**"
    assert vehicle["last_charge"]["location"] == "**REDACTED**"
    assert vehicle["vehicle"]["vin_masked"] == "**REDACTED**"
    # Useful data is kept.
    assert vehicle["state"]["values"]["BatteryLevel"]["value"] == 58.2884
    assert diag["abilities"] == ["lecture"]
