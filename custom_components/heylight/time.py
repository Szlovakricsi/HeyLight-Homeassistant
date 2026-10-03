"""Configuration time entities for HeyLight timing."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
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
    entities: list[TimeEntity] = []
    for node in coordinator.network.nodes:
        if not is_supported_node(node):
            continue
        timing = get_timing_state(coordinator, node)
        if not timing.supported:
            continue
        entities.extend(
            [
                HeylightTurnOnTime(coordinator, node, timing),
                HeylightTurnOffTime(coordinator, node, timing),
            ]
        )
    async_add_entities(entities)


class _HeylightTimingTime(TimeEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-outline"

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


class HeylightTurnOnTime(_HeylightTimingTime):
    _attr_name = "Turn on time"

    def __init__(self, coordinator, node, timing) -> None:
        super().__init__(coordinator, node, timing)
        self._attr_unique_id = (
            f"{coordinator.network.identifier}_{node.unicast:04x}_turn_on_time"
        )

    @property
    def native_value(self) -> time:
        return self._timing.turn_on_time

    async def async_set_value(self, value: time) -> None:
        self._timing.turn_on_time = value.replace(second=0, microsecond=0)
        await self._timing.async_apply()


class HeylightTurnOffTime(_HeylightTimingTime):
    _attr_name = "Turn off time"

    def __init__(self, coordinator, node, timing) -> None:
        super().__init__(coordinator, node, timing)
        self._attr_unique_id = (
            f"{coordinator.network.identifier}_{node.unicast:04x}_turn_off_time"
        )

    @property
    def native_value(self) -> time:
        return self._timing.turn_off_time

    async def async_set_value(self, value: time) -> None:
        self._timing.turn_off_time = value.replace(second=0, microsecond=0)
        await self._timing.async_apply()
