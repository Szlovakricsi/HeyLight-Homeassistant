"""Diagnostics for HeyLight without exposing mesh keys."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from . import HeylightConfigEntry
from .timing import get_timing_state


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: HeylightConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    network = coordinator.network

    nodes = []
    for node in network.nodes:
        timing = get_timing_state(coordinator, node)
        node_data = {
            "name": node.name,
            "unicast": f"0x{node.unicast:04x}",
            "cid": f"0x{node.cid:04x}",
            "pid": f"0x{node.pid:04x}",
            "firmware": node.firmware_label,
            "product_type": node.product_type,
            "bulb_count": node.bulb_count,
            "vendor_model": node.has_model(0x02110000),
            "time_server": node.has_model(0x1200),
            "time_setup_server": node.has_model(0x1201),
            "scheduler_server": node.has_model(0x1206),
            "scheduler_setup_server": node.has_model(0x1207),
            "timing_supported": timing.supported,
            "time_supported": timing.time_supported,
            "clock_synced": timing.clock_synced,
            "device_time_unix": timing.device_time_unix,
            "clock_offset_seconds": timing.clock_offset_seconds,
            "last_pre_sync_offset_seconds": timing.last_pre_sync_offset_seconds,
            "last_clock_sync_unix": timing.last_clock_sync_unix,
        }
        if timing.loaded:
            node_data["timing"] = {
                "enabled": timing.enabled,
                "repeat": timing.repeat,
                "turn_on_time": timing.turn_on_time.isoformat(timespec="minutes"),
                "turn_off_time": timing.turn_off_time.isoformat(timespec="minutes"),
                "pre_sync_seconds": 90,
                "state_readback_seconds_after_event": [1, 4, 8],
            }
        nodes.append(node_data)

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
        "nodes": nodes,
    }
