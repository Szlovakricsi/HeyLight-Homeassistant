"""Diagnostics for HeyLight without exposing mesh keys."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from . import HeylightConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HeylightConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    network = coordinator.network

    return {
        "network": {
            "mesh_name": network.mesh_name,
            "network_id": network.identifier,
            "available": coordinator.available,
            "connected_address": coordinator.connected_address,
            "reconnect_attempts": coordinator.reconnect_attempts,
            "successful_connections": coordinator.successful_connections,
            "last_connection_error": coordinator.last_connection_error,
            "last_disconnect_reason": coordinator.last_disconnect_reason,
        },
        "nodes": [
            {
                "name": node.name,
                "unicast": f"0x{node.unicast:04x}",
                "cid": f"0x{node.cid:04x}",
                "pid": f"0x{node.pid:04x}",
                "firmware": node.firmware_label,
                "product_type": node.product_type,
                "bulb_count": node.bulb_count,
                "vendor_model": node.has_model(0x02110000),
            }
            for node in network.nodes
        ],
    }
