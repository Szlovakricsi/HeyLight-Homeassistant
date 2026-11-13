"""Bluetooth Mesh Proxy signal strength for HeyLight devices."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeylightConfigEntry
from .const import DOMAIN
from .runtime import is_supported_node


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeylightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        HeylightRSSISensor(coordinator, node)
        for node in coordinator.network.nodes
        if is_supported_node(node)
    )


class HeylightRSSISensor(SensorEntity):
    """RSSI from the most recently heard Bluetooth advertisement."""

    _attr_has_entity_name = True
    _attr_translation_key = "bluetooth_rssi"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False

    def __init__(self, coordinator, node) -> None:
        self._coordinator = coordinator
        uid = f"{coordinator.network.identifier}_{node.unicast:04x}"
        self._attr_unique_id = f"{uid}_bluetooth_rssi"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=node.name,
            manufacturer="HeyLight / Telink",
            model=f"RGB Light String PID 0x{node.pid:04X}",
            sw_version=node.firmware_label,
        )

    @property
    def native_value(self) -> int | None:
        return self._coordinator.rssi_dbm

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "last_advertisement": self._coordinator.rssi_last_seen_at,
            "proxy_address": self._coordinator.rssi_address,
            "bluetooth_adapter": self._coordinator.rssi_source,
            "measurement_age_seconds": self._coordinator.rssi_age_seconds,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_rssi_listener(self._handle_rssi)
        )

    @callback
    def _handle_rssi(self) -> None:
        self.async_write_ha_state()
