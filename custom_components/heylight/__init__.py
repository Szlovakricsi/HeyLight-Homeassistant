"""HeyLight Home Assistant integration."""

from __future__ import annotations

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

type HeylightConfigEntry = ConfigEntry[HeylightCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: HeylightConfigEntry
) -> bool:
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
