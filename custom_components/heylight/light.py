"""Light entities for HeyLight."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
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
from homeassistant.util import dt as dt_util

from . import HeylightConfigEntry
from .const import DOMAIN
from .runtime import (
    EFFECT_TO_SCENE,
    get_runtime,
    is_supported_node,
)
from .timing import get_timing_state

_LOGGER = logging.getLogger(__name__)
_TIMER_REFRESH_DELAY = 3


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
        self._timing = get_timing_state(coordinator, node)
        self._refresh_task: asyncio.Task | None = None
        self._timer_sync_task: asyncio.Task | None = None
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
    def brightness(self) -> int:
        return self._runtime.brightness

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

            restored_brightness = last.attributes.get(ATTR_BRIGHTNESS)
            if restored_brightness is not None:
                try:
                    self._runtime.brightness = max(
                        1, min(255, int(restored_brightness))
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
        self.async_on_remove(
            self._timing.add_listener(self._timing_changed)
        )

        self.async_write_ha_state()
        if self._coordinator.available:
            self._schedule_refresh()
        self._reschedule_timer_sync()

    async def async_will_remove_from_hass(self) -> None:
        for task in (self._refresh_task, self._timer_sync_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(
                task
                for task in (self._refresh_task, self._timer_sync_task)
                if task is not None
            ),
            return_exceptions=True,
        )
        self._refresh_task = None
        self._timer_sync_task = None
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
        self._reschedule_timer_sync()

    @callback
    def _timing_changed(self) -> None:
        """Re-arm the HA-side readback helper after timer settings change."""
        self._reschedule_timer_sync()

    def _schedule_refresh(self) -> None:
        """Query physical power once without continuously polling the mesh."""
        if self.hass is None or not self._coordinator.available:
            return
        if self._refresh_task is not None and not self._refresh_task.done():
            return
        self._refresh_task = self.hass.async_create_background_task(
            self.async_refresh_state(),
            f"HeyLight refresh {self._node.unicast:04x}",
        )

    def _reschedule_timer_sync(self) -> None:
        """Schedule a power readback shortly after the next device timer event.

        The previous 5-second continuous E1 polling was intentionally removed.
        Some Telink light-string firmware becomes unreliable when repeatedly
        queried while its on-device Scheduler is active. We only need a
        readback after the known Scheduler transition to keep Home Assistant's
        light state synchronized.
        """
        if self.hass is None:
            return
        if self._timer_sync_task is not None:
            self._timer_sync_task.cancel()
            self._timer_sync_task = None
        if not self._timing.supported or not self._timing.enabled:
            return
        self._timer_sync_task = self.hass.async_create_background_task(
            self._timer_sync_loop(),
            f"HeyLight timer state sync {self._node.unicast:04x}",
        )

    def _next_timer_datetime(self):
        """Return the next configured on/off timer transition in local time."""
        now = dt_util.now()
        candidates = []
        for configured in (
            self._timing.turn_on_time,
            self._timing.turn_off_time,
        ):
            target = now.replace(
                hour=configured.hour,
                minute=configured.minute,
                second=configured.second,
                microsecond=0,
            )
            if self._timing.repeat:
                if target <= now:
                    target += timedelta(days=1)
                candidates.append(target)
            elif target > now:
                candidates.append(target)
        return min(candidates) if candidates else None

    async def _timer_sync_loop(self) -> None:
        """Read power just after each configured Scheduler transition."""
        try:
            while self._timing.enabled:
                target = self._next_timer_datetime()
                if target is None:
                    return
                delay = max(
                    0.0,
                    (target - dt_util.now()).total_seconds()
                    + _TIMER_REFRESH_DELAY,
                )
                await asyncio.sleep(delay)
                if self._coordinator.available:
                    await self.async_refresh_state()
                if not self._timing.repeat:
                    # A non-repeating setup may still have the second event
                    # later today, so loop once more and recalculate.
                    continue
        except asyncio.CancelledError:
            raise

    async def async_refresh_state(self) -> None:
        try:
            state = await self._coordinator._run_connected(
                lambda controller: controller.get_power(
                    self._node.unicast
                )
            )
        except Exception as exc:
            _LOGGER.debug(
                "Unable to refresh HeyLight power state for 0x%04x: %s",
                self._node.unicast,
                exc,
            )
            return

        if state is not None and state != self._runtime.is_on:
            self._runtime.is_on = state
            self._runtime.notify()

    async def async_turn_on(self, **kwargs) -> None:
        effect = kwargs.get(ATTR_EFFECT)
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)

        # The device does not reliably publish its current scene. If HA
        # explicitly supplies an effect, colour or brightness, always resend
        # E6 even when it equals restored state. This is especially important
        # for selecting "normal" and for brightness on PID 0xFAC8 firmware 51.
        scene_requested = (
            effect is not None
            or rgb is not None
            or brightness is not None
        )

        if effect is not None:
            if effect not in EFFECT_TO_SCENE:
                raise ValueError(f"unsupported HeyLight effect: {effect}")
            self._runtime.effect = effect

        if rgb is not None:
            self._runtime.colors[0] = tuple(
                max(0, min(255, int(v))) for v in rgb
            )

        if brightness is not None:
            self._runtime.brightness = max(
                1, min(255, int(brightness))
            )

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

        # Brightness is applied by runtime.active_colors() to the E6 scene
        # colours. The standalone F3 command exists in the APK but did not
        # physically affect this tested PID/firmware, so it is not used here.
        if scene_requested:
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
            and self._runtime.palette_slot_available(self._index)
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
        if self._runtime.is_on and self._runtime.palette_slot_available(self._index):
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
