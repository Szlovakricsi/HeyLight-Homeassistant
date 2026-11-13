"""Manual Bluetooth Mesh Proxy reconnect controls for HeyLight."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant

from . import HeylightConfigEntry
from .const import DOMAIN
from .runtime import is_supported_node


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeylightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Offer a reconnect button on each supported HeyLight device."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeylightReconnectButton(coordinator, node)
        for node in coordinator.network.nodes
        if is_supported_node(node)
    )


class HeylightReconnectButton(ButtonEntity):
    """Restart the shared mesh proxy connection without resetting pairing."""

    _attr_has_entity_name = True
    _attr_translation_key = "reconnect_mesh_proxy"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bluetooth-connect"
    _attr_should_poll = False

    def __init__(self, coordinator, node) -> None:
        self._coordinator = coordinator
        uid = f"{coordinator.network.identifier}_{node.unicast:04x}"
        self._attr_unique_id = f"{uid}_reconnect_mesh_proxy"
        # Match the existing light device so the button is easy to find.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=node.name,
            manufacturer="HeyLight / Telink",
            model=f"RGB Light String PID 0x{node.pid:04X}",
            sw_version=node.firmware_label,
        )

    async def async_press(self) -> None:
        """Drop any stale link and immediately wake the ongoing retry loop."""
        await self._coordinator.async_force_reconnect()
