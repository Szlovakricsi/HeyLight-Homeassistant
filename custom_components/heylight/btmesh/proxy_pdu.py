"""Mesh Proxy PDU SAR framing.

Derived from dasimon135/ha-bluetooth-mesh (MIT), copyright David Simon.
"""

from .errors import BtMeshError

SAR_COMPLETE = 0b00
SAR_FIRST = 0b01
SAR_CONTINUATION = 0b10
SAR_LAST = 0b11

MSG_TYPE_NETWORK_PDU = 0x00
MSG_TYPE_MESH_BEACON = 0x01
MSG_TYPE_PROXY_CONFIG = 0x02


class ProxyPDUError(BtMeshError):
    """Proxy PDU framing error."""


def _header(sar: int, msg_type: int) -> int:
    return (sar << 6) | msg_type


def segment(msg_type: int, payload: bytes, mtu: int) -> list[bytes]:
    if mtu < 2:
        raise ProxyPDUError("MTU leaves no room for Proxy PDU payload")
    chunk = mtu - 1
    if len(payload) <= chunk:
        return [bytes([_header(SAR_COMPLETE, msg_type)]) + payload]

    chunks = [payload[i : i + chunk] for i in range(0, len(payload), chunk)]
    frames: list[bytes] = []
    for index, part in enumerate(chunks):
        if index == 0:
            sar = SAR_FIRST
        elif index == len(chunks) - 1:
            sar = SAR_LAST
        else:
            sar = SAR_CONTINUATION
        frames.append(bytes([_header(sar, msg_type)]) + part)
    return frames


class Reassembler:
    def __init__(self) -> None:
        self._msg_type: int | None = None
        self._buffer = bytearray()

    def _reset(self) -> None:
        self._msg_type = None
        self._buffer = bytearray()

    def feed(self, frame: bytes) -> tuple[int, bytes] | None:
        if not frame:
            self._reset()
            raise ProxyPDUError("empty Proxy PDU")

        sar = frame[0] >> 6
        msg_type = frame[0] & 0x3F
        payload = frame[1:]
        in_progress = self._msg_type is not None

        if sar == SAR_COMPLETE:
            if in_progress:
                self._reset()
                raise ProxyPDUError("complete frame during reassembly")
            return msg_type, payload

        if sar == SAR_FIRST:
            if in_progress:
                self._reset()
                raise ProxyPDUError("new first segment during reassembly")
            self._msg_type = msg_type
            self._buffer = bytearray(payload)
            return None

        if not in_progress:
            raise ProxyPDUError("continuation without first segment")
        if msg_type != self._msg_type:
            self._reset()
            raise ProxyPDUError("message type changed during reassembly")

        self._buffer.extend(payload)
        if sar == SAR_LAST:
            result = (msg_type, bytes(self._buffer))
            self._reset()
            return result
        return None
