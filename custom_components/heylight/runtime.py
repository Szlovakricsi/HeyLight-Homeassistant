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
    "wave up": 27,
    "wave down": 22,
    "flag": 23,
    "head up": 24,
    "vertical wave": 25,
    "snake": 26,
}


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
    def palette_color_slots(self) -> int:
        """Number of independent colours supported by the active scene."""
        scene = self.scene
        if scene in {13, 21, 26}:
            return 2
        if scene in {7, 8, 9, 11, 12, 19, 22, 23, 25, 27}:
            return 3
        return 1

    def palette_slot_available(self, index: int) -> bool:
        return index < self.palette_color_slots

    @property
    def palette_controls_available(self) -> bool:
        return self.palette_color_slots > 1

    def active_colors(self) -> list[tuple[int, int, int]]:
        slots = self.palette_color_slots
        result = [self.colors[0]]
        for index in (1, 2):
            if index >= slots:
                break
            if self.color_enabled[index]:
                result.append(self.colors[index])
        return result[:slots]

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
