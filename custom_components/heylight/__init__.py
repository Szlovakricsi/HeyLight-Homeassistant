"""HeyLight Home Assistant integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SHARE_JSON, DOMAIN
from .coordinator import HeylightCoordinator
from .share import parse_share_text

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.TIME,
]

FRONTEND_SCRIPT_URL = "/heylight/heylight-card.js"
_DATA_FRONTEND_REGISTERED = "frontend_registered"

type HeylightConfigEntry = ConfigEntry[HeylightCoordinator]


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Expose and auto-load the bundled HeyLight dashboard card."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_DATA_FRONTEND_REGISTERED):
        return

    card_path = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/heylight",
                str(card_path),
                False,
            )
        ]
    )
    hass.data.setdefault("frontend_extra_module_url", set()).add(
        FRONTEND_SCRIPT_URL
    )
    domain_data[_DATA_FRONTEND_REGISTERED] = True


async def async_setup_entry(
    hass: HomeAssistant, entry: HeylightConfigEntry
) -> bool:
    await _async_register_frontend(hass)

    network = parse_share_text(entry.data[CONF_SHARE_JSON])
    coordinator = HeylightCoordinator(hass, entry.entry_id, network)
    await coordinator.async_start()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: HeylightConfigEntry
) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded
