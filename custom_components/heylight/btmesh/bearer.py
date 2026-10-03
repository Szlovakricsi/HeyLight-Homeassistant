"""GATT Mesh Proxy bearer."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ..const import PROXY_DATA_IN, PROXY_DATA_OUT
from .proxy_pdu import Reassembler, segment

_LOGGER = logging.getLogger(__name__)

ATT_HEADER_LEN = 3
DEFAULT_MAX_FRAME = 20


class GattProxyBearer:
    """Proxy SAR framing on a connected bleak-compatible client."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._reassembler = Reassembler()
        self._on_message: Callable[[int, bytes], None] | None = None
        self._started = False

    @property
    def max_frame(self) -> int:
        try:
            mtu = int(self._client.mtu_size)
        except Exception:
            mtu = 0
        if mtu - ATT_HEADER_LEN < 2:
            return DEFAULT_MAX_FRAME
        return mtu - ATT_HEADER_LEN

    async def start(
        self, on_message: Callable[[int, bytes], None]
    ) -> None:
        self._on_message = on_message
        try:
            async with asyncio.timeout(5):
                await self._client.start_notify(
                    PROXY_DATA_OUT, self._handle_notify
                )
        except TimeoutError:
            # Some proxy backends start notifications before the await resolves.
            _LOGGER.warning(
                "HeyLight proxy notification subscription did not confirm "
                "within 5 seconds; continuing"
            )
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        try:
            await self._client.stop_notify(PROXY_DATA_OUT)
        except Exception:
            _LOGGER.debug("stop_notify failed", exc_info=True)

    async def send(self, msg_type: int, payload: bytes) -> None:
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
