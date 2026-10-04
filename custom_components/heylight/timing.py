"""Shared timing state for HeyLight Scheduler entities."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import time

from homeassistant.util import dt as dt_util

from .btmesh.access import encode_opcode
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
TIME_SERVER_MODEL = 0x1200
TIME_SETUP_SERVER_MODEL = 0x1201

TURN_ON_INDEX = 1
TURN_OFF_INDEX = 2

# Bluetooth Mesh Time model opcodes.
_TIME_GET = 0x8237
_TIME_SET = 0x5C
_TIME_STATUS = 0x5D

# Bluetooth Mesh TAI Seconds epoch is 2000-01-01 00:00:00 TAI.
_UNIX_TO_TAI_EPOCH = 946684800
# TAI-UTC has been +37 s since 2017-01-01. This is the value used to
# translate Home Assistant's UTC clock into the Mesh Time state.
_TAI_UTC_DELTA_SECONDS = 37


def _mesh_time_params(now) -> bytes:
    """Build the 10-byte Bluetooth Mesh Time Set state from HA local time."""
    utc_seconds = int(now.timestamp())
    tai_seconds = (
        utc_seconds - _UNIX_TO_TAI_EPOCH + _TAI_UTC_DELTA_SECONDS
    )

    offset = now.utcoffset()
    offset_seconds = int(offset.total_seconds()) if offset is not None else 0
    # Mesh time-zone offset is encoded in 15-minute units with 0x40 == UTC.
    zone_quarters = max(-64, min(191, round(offset_seconds / 900)))
    zone_encoded = (zone_quarters + 0x40) & 0xFF

    # The 16-bit field is Time Authority in bit 0 followed by the encoded
    # 15-bit TAI-UTC Delta. 0x00FF represents a real delta of 0 seconds.
    delta_encoded = _TAI_UTC_DELTA_SECONDS + 0x00FF
    authority_delta = ((delta_encoded & 0x7FFF) << 1) | 0x01

    return (
        int(tai_seconds).to_bytes(5, "little")
        + bytes([0x00])  # Subsecond
        + bytes([0x00])  # Uncertainty
        + authority_delta.to_bytes(2, "little")
        + bytes([zone_encoded])
    )


def _mesh_time_to_unix(params: bytes) -> int | None:
    """Decode a Time Status into a Unix timestamp when the clock is known."""
    if len(params) < 5:
        return None
    tai_seconds = int.from_bytes(params[:5], "little")
    if tai_seconds == 0:
        return None

    delta = _TAI_UTC_DELTA_SECONDS
    if len(params) >= 10:
        authority_delta = int.from_bytes(params[7:9], "little")
        delta_encoded = (authority_delta >> 1) & 0x7FFF
        delta = delta_encoded - 0x00FF

    return tai_seconds + _UNIX_TO_TAI_EPOCH - delta


async def _get_device_time(controller, unicast: int) -> int | None:
    """Read the device Time state, returning Unix seconds or None."""
    try:
        msg = await controller._node.request(
            unicast,
            encode_opcode(_TIME_GET),
            _TIME_STATUS,
            timeout=5.0,
        )
    except TimeoutError:
        return None
    return _mesh_time_to_unix(msg.params)


async def _set_device_time(controller, unicast: int) -> int | None:
    """Synchronize the device clock from Home Assistant and return readback."""
    now = dt_util.now()
    try:
        msg = await controller._node.request(
            unicast,
            encode_opcode(_TIME_SET) + _mesh_time_params(now),
            _TIME_STATUS,
            timeout=5.0,
        )
    except TimeoutError:
        return None
    return _mesh_time_to_unix(msg.params)


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
        self.clock_synced = False
        self.device_time_unix: int | None = None
        self.clock_offset_seconds: int | None = None
        self.last_pre_sync_offset_seconds: int | None = None
        self.last_clock_sync_unix: int | None = None
        self._lock = asyncio.Lock()
        self._listeners: list[callable] = []

    @property
    def supported(self) -> bool:
        return (
            self.node.has_model(SCHEDULER_SERVER_MODEL)
            and self.node.has_model(SCHEDULER_SETUP_SERVER_MODEL)
        )

    @property
    def time_supported(self) -> bool:
        return (
            self.node.has_model(TIME_SERVER_MODEL)
            and self.node.has_model(TIME_SETUP_SERVER_MODEL)
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

    async def _measure_clock_unlocked(self) -> int | None:
        """Read device time and record its offset from Home Assistant.

        The midpoint of the Bluetooth request is used as the comparison time so
        request/response latency does not look like clock drift.
        Positive values mean the light string clock is ahead of Home Assistant.
        """
        if not self.time_supported:
            self.clock_synced = False
            self.device_time_unix = None
            self.clock_offset_seconds = None
            return None

        started = dt_util.now().timestamp()
        device_time = await self.coordinator._run_connected(
            lambda controller: _get_device_time(
                controller, self.node.unicast
            )
        )
        finished = dt_util.now().timestamp()
        self.device_time_unix = device_time
        if device_time is None:
            self.clock_offset_seconds = None
            self.clock_synced = False
            return None

        reference = round((started + finished) / 2)
        self.clock_offset_seconds = int(device_time - reference)
        self.clock_synced = abs(self.clock_offset_seconds) <= 2
        return self.clock_offset_seconds

    async def _sync_clock_unlocked(self) -> None:
        """Measure drift, then synchronize the Mesh Time state from HA."""
        if not self.time_supported:
            self.clock_synced = False
            return

        self.last_pre_sync_offset_seconds = await self._measure_clock_unlocked()

        readback = await self.coordinator._run_connected(
            lambda controller: _set_device_time(
                controller, self.node.unicast
            )
        )
        self.device_time_unix = readback
        self.last_clock_sync_unix = int(dt_util.now().timestamp())

        if readback is None:
            self.clock_synced = False
            self.clock_offset_seconds = None
            return

        self.clock_offset_seconds = (
            readback - int(dt_util.now().timestamp())
        )
        self.clock_synced = abs(self.clock_offset_seconds) <= 2

    async def async_sync_clock(self) -> None:
        """Synchronize only the device clock without rewriting timer slots."""
        if not self.time_supported:
            return
        async with self._lock:
            await self._sync_clock_unlocked()

    async def async_measure_clock(self) -> int | None:
        """Measure and return current device clock offset in seconds."""
        if not self.time_supported:
            return None
        async with self._lock:
            return await self._measure_clock_unlocked()

    async def async_refresh(self) -> None:
        """Read Heylight's two Scheduler slots and current Mesh Time state."""
        if not self.supported:
            return
        async with self._lock:
            if self.time_supported:
                await self._measure_clock_unlocked()

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
            # HeyLight 2.3.18 uses its DAY alarm type with the current local
            # month/day when Repeat is disabled.
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
        """Synchronize time, then write both timing slots like the app."""
        if not self.supported:
            return
        async with self._lock:
            await self._sync_clock_unlocked()

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
