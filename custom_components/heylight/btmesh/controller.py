"""HeyLight Telink vendor controller."""

from __future__ import annotations

import asyncio
import logging

from ..const import HEYLIGHT_COMPANY_ID, HEYLIGHT_PRODUCT_CATEGORY
from .access import encode_opcode, vendor_opcode
from .bearer import GattProxyBearer
from .node import MeshNode
from .proxy_pdu import MSG_TYPE_NETWORK_PDU, MSG_TYPE_PROXY_CONFIG

_LOGGER = logging.getLogger(__name__)

_POWER_SET = vendor_opcode(0xE0, HEYLIGHT_COMPANY_ID)
_POWER_GET = vendor_opcode(0xE1, HEYLIGHT_COMPANY_ID)
_POWER_STATUS = vendor_opcode(0xE3, HEYLIGHT_COMPANY_ID)
_SCENE_SET = vendor_opcode(0xE6, HEYLIGHT_COMPANY_ID)
_BRIGHTNESS_SET = vendor_opcode(0xF3, HEYLIGHT_COMPANY_ID)

# Heylight 2.3.18 uses three different E6 payload layouts depending on
# the scene. These sets are copied from btsigTelink.changeScene().
_SCENE_SINGLE_COLOR = frozenset({0, 1, 2, 3, 4, 5, 6, 10, 14, 15, 16, 17, 18, 24, 33, 37, 39, 49, 50, 51})
_SCENE_MULTI_COLOR = frozenset({7, 8, 9, 11, 12, 19, 20, 22, 23, 25, 27, 28, 29, 30, 31, 32, 35, 36, 38, 40, 41, 43, 44, 45, 52, 53})
_SCENE_DUAL_COLOR = frozenset({13, 21, 26, 34, 42})

_SPECIAL_SPEED_SCENES = frozenset({1, 3, 5, 8, 9})
_SPEED_DELAY_200 = {
    1: 4,
    2: 3,
    3: 2,
    4: 1,
    5: -1,
    6: -2,
    7: -3,
    8: -4,
    9: -5,
    10: -6,
}

_GAMMA = (
    0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1,2,
    2,2,2,2,2,2,3,3,3,3,3,4,4,4,4,4,5,5,5,5,6,6,6,6,7,7,7,8,8,8,9,9,
    9,10,10,10,11,11,11,12,12,13,13,14,14,14,15,15,16,16,17,17,18,18,19,
    19,20,20,21,22,22,23,23,24,24,25,26,26,27,28,28,29,30,30,31,32,32,33,
    34,35,35,36,37,38,39,39,40,41,42,43,43,44,45,46,47,48,49,50,51,52,53,
    53,54,55,56,57,58,59,60,62,63,64,65,66,67,68,69,70,71,73,74,75,76,77,
    78,80,81,82,83,85,86,87,88,90,91,92,94,95,96,98,99,100,102,103,105,106,
    108,109,111,112,114,115,117,118,120,121,123,124,126,127,129,131,132,134,
    136,137,139,141,142,144,146,148,149,151,153,155,156,158,160,162,164,166,
    167,169,171,173,175,177,179,181,183,185,187,189,191,193,195,197,199,201,
    203,205,207,210,212,214,216,218,220,223,225,227,229,232,234,236,239,241,
    243,246,248,250,253,255
)


class HeylightMeshController:
    """One held Mesh Proxy connection."""

    def __init__(
        self,
        bearer: GattProxyBearer,
        *,
        net_key: bytes,
        app_key: bytes,
        iv_index: int,
        src_addr: int,
        seq: int,
    ) -> None:
        self._bearer = bearer
        self._src_addr = src_addr
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._tx_task: asyncio.Task | None = None
        self._node = MeshNode(
            netkey=net_key,
            appkey=app_key,
            iv_index=iv_index,
            src_addr=src_addr,
            send_network_pdu=self._queue.put_nowait,
            seq=seq,
        )

    @property
    def seq(self) -> int:
        return self._node.ctx.seq

    async def start(self) -> None:
        await self._bearer.start(self._on_message)
        self._tx_task = asyncio.create_task(
            self._tx_loop(), name="heylight-mesh-tx"
        )
        # Accept-list filter and our provisioner source address.
        await self._send_proxy_config(b"\x00\x00")
        await self._send_proxy_config(
            b"\x01" + self._src_addr.to_bytes(2, "big")
        )

    async def stop(self) -> None:
        if self._tx_task is not None:
            await self._queue.put(None)
            await self._tx_task
            self._tx_task = None
        await self._bearer.stop()

    async def flush(self) -> None:
        await self._queue.join()

    async def _tx_loop(self) -> None:
        while True:
            pdu = await self._queue.get()
            try:
                if pdu is None:
                    return
                await self._bearer.send(MSG_TYPE_NETWORK_PDU, pdu)
            finally:
                self._queue.task_done()

    async def _send_proxy_config(self, message: bytes) -> None:
        pdu = self._node.build_proxy_config_pdu(message)
        await self._bearer.send(MSG_TYPE_PROXY_CONFIG, pdu)

    def _on_message(self, msg_type: int, payload: bytes) -> None:
        if msg_type == MSG_TYPE_NETWORK_PDU:
            self._node.handle_network_pdu(payload)

    @staticmethod
    def _wire_speed(scene: int, speed: int, bulb_count: int) -> int:
        speed = max(1, min(10, int(speed)))

        # Heylight 2.3.18 firmware-family behavior verified on the tested
        # PID 0xFAC8 / firmware "51" string. The product advertises 200
        # addressable positions in its Share Device payload.
        if scene in _SPECIAL_SPEED_SCENES:
            delay = 11 - speed
        elif bulb_count == 200:
            delay = _SPEED_DELAY_200[speed]
        else:
            # Safe fallback: the same table used by the verified 200-light
            # product, rather than transmitting the UI value verbatim.
            delay = _SPEED_DELAY_200[speed]
        return delay & 0xFF

    @staticmethod
    def _process_rgb(
        scene: int, rgb: tuple[int, int, int]
    ) -> tuple[int, int, int]:
        r, g, b = (
            max(0, min(255, int(value))) for value in rgb
        )
        r = int(_GAMMA[r] * 1.0)
        g = int(_GAMMA[g] * 0.85)
        b = int(_GAMMA[b] * 0.40)

        if r == 0 and g == 0 and scene != 45:
            b = min(2 * b, 122)
        return r, g, b

    async def get_power(
        self, unicast: int, *, timeout: float = 5.0
    ) -> bool | None:
        try:
            msg = await self._node.request(
                unicast,
                encode_opcode(_POWER_GET),
                _POWER_STATUS,
                timeout=timeout,
            )
        except TimeoutError:
            return None
        if not msg.params:
            return None
        return bool(msg.params[0])

    async def set_power(
        self, unicast: int, on: bool, *, timeout: float = 5.0
    ) -> bool | None:
        payload = encode_opcode(_POWER_SET) + bytes(
            [1 if on else 0, HEYLIGHT_PRODUCT_CATEGORY]
        )
        try:
            msg = await self._node.request(
                unicast,
                payload,
                _POWER_STATUS,
                timeout=timeout,
            )
        except TimeoutError:
            return None
        if not msg.params:
            return None
        return bool(msg.params[0])

    async def set_brightness(
        self,
        unicast: int,
        brightness: int,
        *,
        product_category: int = HEYLIGHT_PRODUCT_CATEGORY,
    ) -> None:
        """Set global output brightness through Heylight vendor opcode F3."""
        value = max(0, min(255, int(brightness)))
        payload = (
            encode_opcode(_BRIGHTNESS_SET)
            + bytes([_GAMMA[value], product_category & 0xFF])
        )
        self._node.send_access(unicast, payload)
        await self.flush()

    @staticmethod
    def scene_color_slots(scene: int) -> int:
        """Return how many independent color slots the APK supports."""
        if scene in _SCENE_DUAL_COLOR:
            return 2
        if scene in _SCENE_MULTI_COLOR:
            return 3
        return 1

    async def set_scene(
        self,
        unicast: int,
        scene: int,
        colors: list[tuple[int, int, int]],
        *,
        speed: int,
        bulb_count: int = 200,
    ) -> None:
        """Send E6 using the exact scene-specific Heylight payload layout."""
        if not colors:
            raise ValueError("at least one scene color is required")

        wire_speed = self._wire_speed(scene, speed, bulb_count)
        processed = [
            self._process_rgb(scene, color)
            for color in list(colors[:3])
        ]
        params: list[int] = [scene & 0xFF, wire_speed]

        if scene in _SCENE_DUAL_COLOR:
            first = processed[0]
            second = processed[1] if len(processed) > 1 else first
            params.extend(
                [
                    2,
                    0,
                    first[0],
                    first[1],
                    first[2],
                    0,
                    second[0],
                    second[1],
                    second[2],
                ]
            )
        elif scene in _SCENE_MULTI_COLOR:
            params.append(len(processed))
            for r, g, b in processed:
                params.extend([0, r, g, b])
        else:
            r, g, b = processed[0]
            params.extend([1, 0, r, g, b])

        params.append(HEYLIGHT_PRODUCT_CATEGORY)
        self._node.send_access(
            unicast,
            encode_opcode(_SCENE_SET) + bytes(params),
        )
        await self.flush()

