"""Effect speed control for HeyLight."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import HeylightConfigEntry
from .const import DOMAIN
from .runtime import get_runtime, is_supported_node


def _device_info(coordinator, node) -> DeviceInfo:
    uid = f"{coordinator.network.identifier}_{node.unicast:04x}"
    return DeviceInfo(
        identifiers={(DOMAIN, uid)},
        name=node.name,
        manufacturer="HeyLight / Telink",
        model=f"RGB Light String PID 0x{node.pid:04X}",
        sw_version=node.firmware_label,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeylightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities = []
    for node in coordinator.network.nodes:
        if is_supported_node(node):
            entities.append(
                HeylightEffectSpeed(
                    coordinator,
                    node,
                    get_runtime(coordinator, node),
                )
            )
    async_add_entities(entities)


class HeylightEffectSpeed(NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "Effect speed"
    _attr_icon = "mdi:speedometer"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, node, runtime) -> None:
        self._coordinator = coordinator
        self._node = node
        self._runtime = runtime
        self._attr_unique_id = (
            f"{coordinator.network.identifier}_{node.unicast:04x}"
            "_effect_speed"
        )
        self._attr_device_info = _device_info(coordinator, node)

    @property
    def available(self) -> bool:
        return (
            self._coordinator.available
            and self._runtime.effect != "normal"
        )

    @property
    def native_value(self) -> float:
        return float(self._runtime.speed)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                value = int(round(float(last.state)))
            except (TypeError, ValueError):
                value = self._runtime.speed
            if 1 <= value <= 10:
                self._runtime.speed = value

        self.async_on_remove(
            self._runtime.add_listener(self._runtime_changed)
        )
        self.async_on_remove(
            self._coordinator.async_add_listener(
                self._availability_changed
            )
        )

    @callback
    def _runtime_changed(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _availability_changed(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        self._runtime.speed = max(1, min(10, int(round(value))))
        self._runtime.notify()
        if self._runtime.is_on and self._runtime.effect != "normal":
            await self._runtime.apply_scene()
