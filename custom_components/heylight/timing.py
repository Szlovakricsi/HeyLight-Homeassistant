"""Shared timing state for HeyLight Scheduler entities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import time

from homeassistant.util import dt as dt_util

from .btmesh.controller import (
    SCHEDULER_ACTION_NONE,
    SCHEDULER_ACTION_OFF,
    SCHEDULER_ACTION_ON,
    SCHEDULER_DAY_ANY,
    SCHEDULER_DAY_OF_WEEK_ALL,
    SCHEDULER_MONTH_ALL,
    SCHEDULER_YEAR_ANY,
    SchedulerEntry,
)

SCHEDULER_SERVER_MODEL = 0x1206
SCHEDULER_SETUP_SERVER_MODEL = 0x1207

TURN_ON_INDEX = 1
TURN_OFF_INDEX = 2


@dataclass
class HeylightTimingState:
    """Mirror the four timing controls exposed by the Heylight app."""

    coordinator: object
    node: object

    def __post_init__(self) -> None:
        self.enabled = False
        self.repeat = True
        self.turn_on_time = time(8, 30)
        self.turn_off_time = time(17, 30)
        self.loaded = False
        self._lock = asyncio.Lock()
        self._listeners: list[callable] = []

    @property
    def supported(self) -> bool:
        return (
            self.node.has_model(SCHEDULER_SERVER_MODEL)
            and self.node.has_model(SCHEDULER_SETUP_SERVER_MODEL)
        )

    def add_listener(self, listener):
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def async_refresh(self) -> None:
        """Read Heylight's two Scheduler slots from the light string."""
        if not self.supported:
            return
        async with self._lock:
            on_entry = await self.coordinator._run_connected(
                lambda controller: controller.get_scheduler_entry(
                    self.node.unicast, TURN_ON_INDEX
                )
            )
            off_entry = await self.coordinator._run_connected(
                lambda controller: controller.get_scheduler_entry(
                    self.node.unicast, TURN_OFF_INDEX
                )
            )
            if on_entry is not None:
                if 0 <= on_entry.hour <= 23 and 0 <= on_entry.minute <= 59:
                    self.turn_on_time = time(on_entry.hour, on_entry.minute)
                self.repeat = on_entry.day_of_week == SCHEDULER_DAY_OF_WEEK_ALL
                self.enabled = on_entry.action != SCHEDULER_ACTION_NONE
            if off_entry is not None:
                if 0 <= off_entry.hour <= 23 and 0 <= off_entry.minute <= 59:
                    self.turn_off_time = time(off_entry.hour, off_entry.minute)
                self.enabled = self.enabled and off_entry.action != SCHEDULER_ACTION_NONE
            self.loaded = on_entry is not None or off_entry is not None
            self.notify()

    def _entry(self, index: int, at: time, action: int) -> SchedulerEntry:
        now = dt_util.now()
        if self.repeat:
            month = SCHEDULER_MONTH_ALL
            day = SCHEDULER_DAY_ANY
            day_of_week = SCHEDULER_DAY_OF_WEEK_ALL
        else:
            # Match Heylight 2.3.18 exactly: Repeat OFF stores the current
            # month/day and clears the day-of-week mask.
            month = 1 << (now.month - 1)
            day = now.day
            day_of_week = 0

        return SchedulerEntry(
            index=index,
            year=SCHEDULER_YEAR_ANY,
            month=month,
            day=day,
            hour=at.hour,
            minute=at.minute,
            second=0,
            day_of_week=day_of_week,
            action=action if self.enabled else SCHEDULER_ACTION_NONE,
            transition_time=0,
            scene_number=0,
        )

    async def async_apply(self) -> None:
        """Write both timing slots using the same layout as the app."""
        if not self.supported:
            return
        async with self._lock:
            on_entry = self._entry(
                TURN_ON_INDEX, self.turn_on_time, SCHEDULER_ACTION_ON
            )
            off_entry = self._entry(
                TURN_OFF_INDEX, self.turn_off_time, SCHEDULER_ACTION_OFF
            )
            await self.coordinator._run_connected(
                lambda controller: controller.set_scheduler_entry(
                    self.node.unicast, on_entry
                )
            )
            await self.coordinator._run_connected(
                lambda controller: controller.set_scheduler_entry(
                    self.node.unicast, off_entry
                )
            )
            self.loaded = True
            self.notify()


def get_timing_state(coordinator, node) -> HeylightTimingState:
    states = getattr(coordinator, "_heylight_timing_states", None)
    if states is None:
        states = {}
        setattr(coordinator, "_heylight_timing_states", states)
    state = states.get(node.unicast)
    if state is None:
        state = HeylightTimingState(coordinator, node)
        states[node.unicast] = state
    return state
