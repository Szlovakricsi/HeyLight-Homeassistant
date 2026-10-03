"""Light entities for HeyLight."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components.light import (
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import HeylightConfigEntry
from .const import DOMAIN
from .runtime import (
    EFFECT_TO_SCENE,
    get_runtime,
    is_supported_node,
)

_LOGGER = logging.getLogger(__name__)


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
    entities: list[LightEntity] = []

    for node in coordinator.network.nodes:
        if not is_supported_node(node):
            continue
        runtime = get_runtime(coordinator, node)
        entities.extend(
            [
                HeylightLight(coordinator, node, runtime),
                PaletteColor(coordinator, node, runtime, 1),
                PaletteColor(coordinator, node, runtime, 2),
            ]
        )

    async_add_entities(entities)


class HeylightLight(LightEntity, RestoreEntity):
    """Physical HeyLight string."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(EFFECT_TO_SCENE)

    def __init__(self, coordinator, node, runtime) -> None:
        self._coordinator = coordinator
        self._node = node
        self._runtime = runtime
        self._refresh_task: asyncio.Task | None = None
        self._attr_unique_id = (
            f"{coordinator.network.identifier}_{node.unicast:04x}"
        )
        self._attr_device_info = _device_info(coordinator, node)

    @property
    def available(self) -> bool:
        return self._coordinator.available

    @property
    def is_on(self) -> bool | None:
        return self._runtime.is_on

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        return self._runtime.colors[0]

    @property
    def effect(self) -> str:
        return self._runtime.effect

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        if last is not None:
            rgb = last.attributes.get(ATTR_RGB_COLOR)
            if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
                try:
                    self._runtime.colors[0] = tuple(
                        max(0, min(255, int(v))) for v in rgb
                    )
                except (TypeError, ValueError):
                    pass

            effect = last.attributes.get(ATTR_EFFECT)
            if effect in EFFECT_TO_SCENE:
                self._runtime.effect = effect

            self._runtime.is_on = last.state == STATE_ON

        self.async_on_remove(
            self._runtime.add_listener(self._runtime_changed)
        )
        self.async_on_remove(
            self._coordinator.async_add_listener(
                self._availability_changed
            )
        )

        self.async_write_ha_state()
        if self._coordinator.available:
            self._schedule_refresh()

    async def async_will_remove_from_hass(self) -> None:
        if self._refresh_task is not None:
            self._refresh_task.cancel()
        await super().async_will_remove_from_hass()

    @callback
    def _runtime_changed(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _availability_changed(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()
        if self._coordinator.available:
            self._schedule_refresh()

    def _schedule_refresh(self) -> None:
        if self.hass is None:
            return
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._refresh_task = self.hass.async_create_background_task(
            self.async_refresh_state(),
            f"HeyLight refresh {self._node.unicast:04x}",
        )

    async def async_refresh_state(self) -> None:
        try:
            state = await self._coordinator._run_connected(
                lambda controller: controller.get_power(
                    self._node.unicast
                )
            )
        except Exception:
            return

        if state is not None:
            self._runtime.is_on = state
            self._runtime.notify()

    async def async_turn_on(self, **kwargs) -> None:
        effect = kwargs.get(ATTR_EFFECT)
        rgb = kwargs.get(ATTR_RGB_COLOR)
        scene_changed = False

        if effect is not None:
            if effect not in EFFECT_TO_SCENE:
                raise ValueError(f"unsupported HeyLight effect: {effect}")
            if effect != self._runtime.effect:
                self._runtime.effect = effect
                scene_changed = True

        if rgb is not None:
            new_rgb = tuple(
                max(0, min(255, int(v))) for v in rgb
            )
            if new_rgb != self._runtime.colors[0]:
                self._runtime.colors[0] = new_rgb
                scene_changed = True

        self._runtime.is_on = True
        self._runtime.notify()

        result = await self._coordinator._run_connected(
            lambda controller: controller.set_power(
                self._node.unicast, True
            )
        )
        if result is not None:
            self._runtime.is_on = result
            self._runtime.notify()

        if scene_changed:
            await self._runtime.apply_scene()

    async def async_turn_off(self, **kwargs) -> None:
        self._runtime.is_on = False
        self._runtime.notify()

        result = await self._coordinator._run_connected(
            lambda controller: controller.set_power(
                self._node.unicast, False
            )
        )
        if result is not None:
            self._runtime.is_on = result
            self._runtime.notify()


class PaletteColor(LightEntity, RestoreEntity):
    """Optional palette slot 2 or 3.

    Its on/off state enables/disables that color in the effect payload; it
    does not power the physical string.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_icon = "mdi:palette"

    def __init__(self, coordinator, node, runtime, index: int) -> None:
        self._coordinator = coordinator
        self._node = node
        self._runtime = runtime
        self._index = index
        number = index + 1
        self._attr_name = f"Effect color {number}"
        self._attr_unique_id = (
            f"{coordinator.network.identifier}_{node.unicast:04x}"
            f"_effect_color_{number}"
        )
        self._attr_device_info = _device_info(coordinator, node)

    @property
    def available(self) -> bool:
        return (
            self._coordinator.available
            and self._runtime.palette_controls_available
        )

    @property
    def is_on(self) -> bool:
        return self._runtime.color_enabled[self._index]

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        return self._runtime.colors[self._index]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        if last is not None:
            rgb = last.attributes.get(ATTR_RGB_COLOR)
            if isinstance(rgb, (list, tuple)) and len(rgb) == 3:
                try:
                    self._runtime.colors[self._index] = tuple(
                        max(0, min(255, int(v))) for v in rgb
                    )
                except (TypeError, ValueError):
                    pass
            self._runtime.color_enabled[self._index] = (
                last.state == STATE_ON
            )

        self.async_on_remove(
            self._runtime.add_listener(self._runtime_changed)
        )
        self.async_on_remove(
            self._coordinator.async_add_listener(
                self._availability_changed
            )
        )
        self.async_write_ha_state()

    @callback
    def _runtime_changed(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()

    @callback
    def _availability_changed(self) -> None:
        if self.hass is not None:
            self.async_write_ha_state()

    async def _apply_if_active(self) -> None:
        if self._runtime.is_on and self._runtime.effect != "normal":
            await self._runtime.apply_scene()

    async def async_turn_on(self, **kwargs) -> None:
        rgb = kwargs.get(ATTR_RGB_COLOR)
        if rgb is not None:
            self._runtime.colors[self._index] = tuple(
                max(0, min(255, int(v))) for v in rgb
            )
        self._runtime.color_enabled[self._index] = True
        self._runtime.notify()
        await self._apply_if_active()

    async def async_turn_off(self, **kwargs) -> None:
        self._runtime.color_enabled[self._index] = False
        self._runtime.notify()
        await self._apply_if_active()
