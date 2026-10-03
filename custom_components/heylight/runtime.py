"""Shared UI state for HeyLight entities."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from .const import HEYLIGHT_COMPANY_ID, HEYLIGHT_VENDOR_MODEL

DEFAULT_EFFECT = "normal"
DEFAULT_SPEED = 6
DEFAULT_BRIGHTNESS = 255
DEFAULT_COLORS: tuple[tuple[int, int, int], ...] = (
    (255, 255, 255),
    (255, 0, 0),
    (0, 0, 255),
)

# Scene IDs reviewed against Heylight 2.3.18 and then verified on the
# PID 0xFAC8 / firmware 51 light string.
EFFECT_TO_SCENE: dict[str, int] = {
    "normal": 0,
    "flick": 1,
    "flick around": 3,
    "random color": 5,
    "fading": 6,
    "fading adv": 7,
    "color change1": 8,
    "color change2": 9,
    "fall rainbow": 10,
    "fall snake": 11,
    "fall ant": 12,
    "moon beyond stars": 13,
    "collide": 18,
    "little fire": 19,
    "random breath": 21,
    "wave down": 22,
    "flag": 23,
    "head up": 24,
    "vertical wave": 25,
    "snake": 26,
    "wave up": 27,
}

# Physical testing on PID 0xFAC8 / firmware 51 established this capability
# matrix. Scenes 5 and 10 have a fixed internal colour in the Heylight app;
# their scene table contains #ffffff and does not expose a colour editor.
_NO_USER_COLOR_SCENES = frozenset({5, 10})
_DUAL_COLOR_SCENES = frozenset({13, 21, 26})
_MULTI_COLOR_SCENES = frozenset({7, 8, 9, 11, 12, 19, 22, 23, 25, 27})


def is_supported_node(node) -> bool:
    return (
        node.cid == HEYLIGHT_COMPANY_ID
        and node.has_model(HEYLIGHT_VENDOR_MODEL)
    )


@dataclass
class HeylightRuntime:
    coordinator: object
    node: object

    def __post_init__(self) -> None:
        self.is_on: bool | None = None
        self.effect = DEFAULT_EFFECT
        self.speed = DEFAULT_SPEED
        self.brightness = DEFAULT_BRIGHTNESS
        self.colors = list(DEFAULT_COLORS)
        self.color_enabled = [True, False, False]
        self._listeners: list[Callable[[], None]] = []
        self._scene_lock = asyncio.Lock()

    @property
    def scene(self) -> int:
        return EFFECT_TO_SCENE[self.effect]

    @property
    def user_color_available(self) -> bool:
        """Whether the active effect exposes a user-selectable colour."""
        return self.scene not in _NO_USER_COLOR_SCENES

    @property
    def palette_color_slots(self) -> int:
        """Number of independent user-selectable colours for the scene."""
        scene = self.scene
        if scene in _NO_USER_COLOR_SCENES:
            return 0
        if scene in _DUAL_COLOR_SCENES:
            return 2
        if scene in _MULTI_COLOR_SCENES:
            return 3
        return 1

    def palette_slot_available(self, index: int) -> bool:
        return index < self.palette_color_slots

    @property
    def palette_controls_available(self) -> bool:
        return self.palette_color_slots > 1

    def _brightness_scaled(
        self, rgb: tuple[int, int, int]
    ) -> tuple[int, int, int]:
        """Scale RGB value like lowering HSV V without changing saved colour."""
        factor = max(1, min(255, int(self.brightness))) / 255.0
        return tuple(
            max(0, min(255, int(round(channel * factor))))
            for channel in rgb
        )

    def active_colors(self) -> list[tuple[int, int, int]]:
        """Return the colours actually transmitted in the E6 scene payload."""
        scene = self.scene

        # randomColor (5) and fallRainbow (10) are fixed-colour effects in the
        # APK. Both use a hidden #ffffff colourList entry. Sending the previous
        # user-selected RGB here can make fallRainbow fail on firmware 51, so
        # always transmit the app's fixed white while still applying HA
        # brightness to that value.
        if scene in _NO_USER_COLOR_SCENES:
            return [self._brightness_scaled((255, 255, 255))]

        slots = self.palette_color_slots
        result = [self.colors[0]]
        for index in (1, 2):
            if index >= slots:
                break
            if self.color_enabled[index]:
                result.append(self.colors[index])

        # Keep the original UI colours untouched and scale only transmitted
        # E6 values. Returning to 100% therefore restores the exact colour.
        return [self._brightness_scaled(color) for color in result[:slots]]

    def add_listener(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def apply_scene(self) -> None:
        async with self._scene_lock:
            await self.coordinator._run_connected(
                lambda controller: controller.set_scene(
                    self.node.unicast,
                    self.scene,
                    self.active_colors(),
                    speed=self.speed,
                    bulb_count=self.node.bulb_count,
                )
            )


def get_runtime(coordinator, node) -> HeylightRuntime:
    states = getattr(coordinator, "_heylight_states", None)
    if states is None:
        states = {}
        setattr(coordinator, "_heylight_states", states)

    runtime = states.get(node.unicast)
    if runtime is None:
        runtime = HeylightRuntime(coordinator, node)
        states[node.unicast] = runtime
    return runtime
