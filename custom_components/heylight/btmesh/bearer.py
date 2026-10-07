"""GATT Mesh Proxy bearer."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ..const import PROXY_DATA_IN, PROXY_DATA_OUT
from .proxy_pdu import Reassembler, segment

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_FRAME = 20
START_NOTIFY_TIMEOUT = 1.0


class GattProxyBearer:
    """Proxy SAR framing on a connected bleak-compatible client."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._reassembler = Reassembler()
        self._on_message: Callable[[int, bytes], None] | None = None
        self._started = False
        self._subscribe_task: asyncio.Task | None = None
        self.failure: BaseException | None = None

    @property
    def max_frame(self) -> int:
        """Use the minimum ATT payload and avoid BlueZ's mtu_size warning."""
        return DEFAULT_MAX_FRAME

    async def start(
        self, on_message: Callable[[int, bytes], None]
    ) -> None:
        self._on_message = on_message
        task = asyncio.ensure_future(
            self._client.start_notify(
                PROXY_DATA_OUT, self._handle_notify
            )
        )
        try:
            await asyncio.wait_for(
                asyncio.shield(task), START_NOTIFY_TIMEOUT
            )
        except TimeoutError:
            task.add_done_callback(self._on_late_subscribe)
            self._subscribe_task = task
            _LOGGER.debug(
                "HeyLight start_notify not confirmed after %.1fs; "
                "leaving subscription task running",
                START_NOTIFY_TIMEOUT,
            )
        except Exception:
            task.cancel()
            raise
        self._started = True

    def _on_late_subscribe(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            self.failure = exc
            _LOGGER.warning(
                "HeyLight Mesh Proxy notification subscription failed: %s",
                exc,
            )

    async def stop(self) -> None:
        pending, self._subscribe_task = self._subscribe_task, None
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

        if not self._started:
            return
        self._started = False
        try:
            await self._client.stop_notify(PROXY_DATA_OUT)
        except Exception:
            _LOGGER.debug("stop_notify failed", exc_info=True)

    async def send(self, msg_type: int, payload: bytes) -> None:
        if self.failure is not None:
            raise RuntimeError(
                f"Mesh Proxy notification subscription failed: {self.failure}"
            )
        if not bool(getattr(self._client, "is_connected", True)):
            raise ConnectionError("HeyLight Bluetooth link is disconnected")

        for frame in segment(msg_type, payload, self.max_frame):
            await self._client.write_gatt_char(
                PROXY_DATA_IN, frame, response=False
            )

    def _handle_notify(self, _char: Any, data: bytearray) -> None:
        try:
            complete = self._reassembler.feed(bytes(data))
        except Exception:
            _LOGGER.debug("dropping malformed Proxy PDU", exc_info=True)
            return
        if complete is None or self._on_message is None:
            return
        msg_type, payload = complete
        self._on_message(msg_type, payload)
