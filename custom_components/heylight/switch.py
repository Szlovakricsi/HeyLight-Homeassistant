"""Configuration switches for HeyLight timing."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HeylightConfigEntry
from .light import _device_info
from .runtime import is_supported_node
from .timing import get_timing_state


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeylightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    for node in coordinator.network.nodes:
        if not is_supported_node(node):
            continue
        timing = get_timing_state(coordinator, node)
        if not timing.supported:
            continue
        entities.extend(
            [
                HeylightTimingEnabled(coordinator, node, timing),
                HeylightTimingRepeat(coordinator, node, timing),
            ]
        )
    async_add_entities(entities)


class _HeylightTimingSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, node, timing) -> None:
        self._coordinator = coordinator
        self._node = node
        self._timing = timing
        self._attr_device_info = _device_info(coordinator, node)

    @property
    def available(self) -> bool:
        return self._coordinator.available and self._timing.supported

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._timing.add_listener(self._timing_changed))
        self.async_on_remove(
            self._coordinator.async_add_listener(self._availability_changed)
        )
        if self._coordinator.available and not self._timing.loaded:
            await self._timing.async_refresh()

    @callback
    def _timing_changed(self) -> None:
        self.async_write_ha_state()

    @callback
    def _availability_changed(self) -> None:
        self.async_write_ha_state()


class HeylightTimingEnabled(_HeylightTimingSwitch):
    _attr_name = "Timing"
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, node, timing) -> None:
        super().__init__(coordinator, node, timing)
        self._attr_unique_id = (
            f"{coordinator.network.identifier}_{node.unicast:04x}_timing"
        )

    @property
    def is_on(self) -> bool:
        return self._timing.enabled

    async def async_turn_on(self, **kwargs) -> None:
        self._timing.enabled = True
        await self._timing.async_apply()

    async def async_turn_off(self, **kwargs) -> None:
        self._timing.enabled = False
        await self._timing.async_apply()


class HeylightTimingRepeat(_HeylightTimingSwitch):
    _attr_name = "Timing repeat"
    _attr_icon = "mdi:repeat"

    def __init__(self, coordinator, node, timing) -> None:
        super().__init__(coordinator, node, timing)
        self._attr_unique_id = (
            f"{coordinator.network.identifier}_{node.unicast:04x}_timing_repeat"
        )

    @property
    def is_on(self) -> bool:
        return self._timing.repeat

    async def async_turn_on(self, **kwargs) -> None:
        self._timing.repeat = True
        await self._timing.async_apply()

    async def async_turn_off(self, **kwargs) -> None:
        self._timing.repeat = False
        await self._timing.async_apply()
