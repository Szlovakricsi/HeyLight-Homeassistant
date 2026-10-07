"""Small provisioner-side Mesh node used by HeyLight."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import NamedTuple

from . import network
from .access import parse_access
from .crypto import k4
from .network import NetworkContext, NetworkError
from .transport import (
    TRANS_MIC_LEN,
    UNSEG_MAX_UPPER_LEN,
    AccessSegment,
    UnsegmentedAccess,
    build_unsegmented_access,
    decrypt_access,
    encrypt_access,
    parse_access_lower,
    segment_access_message,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_TTL = 7
_MAX_INCOMING_SEGMENTED = 16


class ReceivedMessage(NamedTuple):
    src: int
    opcode: int
    params: bytes


class _Waiter(NamedTuple):
    dst: int
    expected_opcode: int
    key: bytes
    akf: bool
    aid: int
    future: asyncio.Future[ReceivedMessage]


@dataclass
class _IncomingSegments:
    """Reassembly state for one segmented Access message."""

    seq_auth: int
    seg_n: int
    akf: bool
    aid: int
    szmic: int
    segments: dict[int, bytes] = field(default_factory=dict)

    @property
    def block_ack(self) -> int:
        value = 0
        for index in self.segments:
            value |= 1 << index
        return value

    @property
    def complete(self) -> bool:
        expected = (1 << (self.seg_n + 1)) - 1
        return self.block_ack == expected

    def upper_pdu(self) -> bytes:
        if not self.complete:
            raise ValueError("segmented message is incomplete")
        return b"".join(
            self.segments[index] for index in range(self.seg_n + 1)
        )


class MeshNode:
    def __init__(
        self,
        *,
        netkey: bytes,
        appkey: bytes,
        iv_index: int,
        src_addr: int,
        send_network_pdu: Callable[[bytes], None],
        seq: int = 0,
    ) -> None:
        self.ctx = NetworkContext(netkey, iv_index, seq)
        self._appkey = appkey
        self._aid = k4(appkey)
        self._iv_index = iv_index
        self._src = src_addr
        self._send = send_network_pdu
        self._waiters: list[_Waiter] = []
        self._incoming_segments: dict[
            tuple[int, int, int, bool, int], _IncomingSegments
        ] = {}

    def _send_access_with_key(
        self,
        dst: int,
        payload: bytes,
        *,
        key: bytes,
        akf: bool,
        aid: int,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        upper_len = len(payload) + TRANS_MIC_LEN

        if upper_len <= UNSEG_MAX_UPPER_LEN:
            seq = self.ctx.next_seq()
            upper = encrypt_access(
                key,
                akf=akf,
                seq=seq,
                src=self._src,
                dst=dst,
                iv_index=self._iv_index,
                access_pdu=payload,
            )
            pdus = [
                (
                    seq,
                    build_unsegmented_access(
                        upper, akf=akf, aid=aid
                    ),
                )
            ]
        else:
            seg_count = (upper_len + 11) // 12
            first_seq = self.ctx.next_seq(seg_count)
            upper = encrypt_access(
                key,
                akf=akf,
                seq=first_seq,
                src=self._src,
                dst=dst,
                iv_index=self._iv_index,
                access_pdu=payload,
            )
            pdus = segment_access_message(
                upper,
                akf=akf,
                aid=aid,
                first_seq=first_seq,
            )

        for seq, lower in pdus:
            self._send(
                network.encode(
                    self.ctx,
                    ctl=False,
                    ttl=ttl,
                    seq=seq,
                    src=self._src,
                    dst=dst,
                    transport_pdu=lower,
                )
            )

    def send_access(
        self, dst: int, payload: bytes, *, ttl: int = DEFAULT_TTL
    ) -> None:
        self._send_access_with_key(
            dst,
            payload,
            key=self._appkey,
            akf=True,
            aid=self._aid,
            ttl=ttl,
        )

    def send_devkey_access(
        self,
        dst: int,
        payload: bytes,
        device_key: bytes,
        *,
        ttl: int = DEFAULT_TTL,
    ) -> None:
        """Send a Config Server message encrypted with the node DeviceKey."""
        if len(device_key) != 16:
            raise ValueError("device_key must be 16 bytes")

        self._send_access_with_key(
            dst,
            payload,
            key=device_key,
            akf=False,
            aid=0,
            ttl=ttl,
        )

    def build_proxy_config_pdu(self, message: bytes) -> bytes:
        return network.encode(
            self.ctx,
            ctl=True,
            ttl=0,
            seq=self.ctx.next_seq(),
            src=self._src,
            dst=0x0000,
            transport_pdu=message,
        )

    def _dispatch_access(
        self,
        *,
        src: int,
        dst: int,
        seq_auth: int,
        akf: bool,
        aid: int,
        upper_pdu: bytes,
    ) -> None:
        """Decrypt an Access payload against the relevant pending request."""
        if akf:
            if aid != self._aid:
                return
            try:
                access_payload = decrypt_access(
                    self._appkey,
                    akf=True,
                    seq=seq_auth,
                    src=src,
                    dst=dst,
                    iv_index=self._iv_index,
                    upper_pdu=upper_pdu,
                )
                opcode, params = parse_access(access_payload)
            except Exception:
                return

            for waiter in tuple(self._waiters):
                if (
                    waiter.akf
                    and waiter.dst == src
                    and waiter.expected_opcode == opcode
                    and not waiter.future.done()
                ):
                    waiter.future.set_result(
                        ReceivedMessage(src, opcode, params)
                    )
                    return
            return

        if aid != 0:
            return

        # DeviceKey traffic carries no AID. Try only DeviceKeys belonging to
        # pending requests from this source.
        for waiter in tuple(self._waiters):
            if waiter.akf or waiter.dst != src or waiter.future.done():
                continue
            try:
                access_payload = decrypt_access(
                    waiter.key,
                    akf=False,
                    seq=seq_auth,
                    src=src,
                    dst=dst,
                    iv_index=self._iv_index,
                    upper_pdu=upper_pdu,
                )
                opcode, params = parse_access(access_payload)
            except Exception:
                continue

            if opcode != waiter.expected_opcode:
                continue

            waiter.future.set_result(ReceivedMessage(src, opcode, params))
            return

    @staticmethod
    def _segment_seq_auth(received_seq: int, seq_zero: int) -> int:
        """Recover SeqAuth's sequence number from SeqZero and a segment seq."""
        candidate = (received_seq & ~0x1FFF) | seq_zero
        if candidate > received_seq:
            candidate -= 0x2000
        if candidate < 0:
            raise ValueError("could not reconstruct segmented SeqAuth")
        return candidate

    def _send_segment_ack(
        self,
        *,
        dst: int,
        seq_zero: int,
        block_ack: int,
        ttl: int,
    ) -> None:
        """Acknowledge received lower-transport Access segments."""
        ack_fields = ((seq_zero & 0x1FFF) << 2).to_bytes(2, "big")
        transport_pdu = (
            b"\x00"
            + ack_fields
            + int(block_ack & 0xFFFFFFFF).to_bytes(4, "big")
        )
        seq = self.ctx.next_seq()
        self._send(
            network.encode(
                self.ctx,
                ctl=True,
                ttl=max(0, min(0x7F, ttl)),
                seq=seq,
                src=self._src,
                dst=dst,
                transport_pdu=transport_pdu,
            )
        )

    def _handle_segment(
        self,
        *,
        pdu,
        segment: AccessSegment,
    ) -> None:
        if segment.seg_n >= 32 or segment.seg_o > segment.seg_n:
            return

        try:
            seq_auth = self._segment_seq_auth(pdu.seq, segment.seq_zero)
        except ValueError:
            return

        key = (
            pdu.src,
            pdu.dst,
            segment.seq_zero,
            segment.akf,
            segment.aid,
        )
        state = self._incoming_segments.get(key)
        if state is None:
            if len(self._incoming_segments) >= _MAX_INCOMING_SEGMENTED:
                # A held GATT proxy normally has only one or two responses in
                # flight. Avoid retaining stale partial messages forever.
                self._incoming_segments.clear()
            state = _IncomingSegments(
                seq_auth=seq_auth,
                seg_n=segment.seg_n,
                akf=segment.akf,
                aid=segment.aid,
                szmic=segment.szmic,
            )
            self._incoming_segments[key] = state
        elif (
            state.seg_n != segment.seg_n
            or state.seq_auth != seq_auth
            or state.szmic != segment.szmic
        ):
            self._incoming_segments.pop(key, None)
            return

        state.segments[segment.seg_o] = segment.segment
        self._send_segment_ack(
            dst=pdu.src,
            seq_zero=segment.seq_zero,
            block_ack=state.block_ack,
            ttl=DEFAULT_TTL,
        )

        if not state.complete:
            return

        self._incoming_segments.pop(key, None)
        if state.szmic:
            # Current HeyLight Config Server responses use a 32-bit TransMIC.
            # Keep this explicit rather than accidentally decrypting a 64-bit
            # segmented Access message with the wrong nonce/MIC assumptions.
            _LOGGER.debug(
                "ignoring segmented Access response with 64-bit TransMIC"
            )
            return

        self._dispatch_access(
            src=pdu.src,
            dst=pdu.dst,
            seq_auth=state.seq_auth,
            akf=state.akf,
            aid=state.aid,
            upper_pdu=state.upper_pdu(),
        )

    def handle_network_pdu(self, raw: bytes) -> None:
        try:
            pdu = network.decode(self.ctx, raw)
        except NetworkError:
            return

        if pdu.ctl or pdu.src == self._src:
            return

        try:
            lower = parse_access_lower(pdu.transport_pdu)
        except Exception:
            return

        if isinstance(lower, AccessSegment):
            self._handle_segment(pdu=pdu, segment=lower)
            return

        if not isinstance(lower, UnsegmentedAccess):
            return

        self._dispatch_access(
            src=pdu.src,
            dst=pdu.dst,
            seq_auth=pdu.seq,
            akf=lower.akf,
            aid=lower.aid,
            upper_pdu=lower.upper_pdu,
        )

    async def _request_with_key(
        self,
        dst: int,
        payload: bytes,
        expected_opcode: int,
        *,
        key: bytes,
        akf: bool,
        aid: int,
        timeout: float,
    ) -> ReceivedMessage:
        fut: asyncio.Future[ReceivedMessage] = (
            asyncio.get_running_loop().create_future()
        )
        waiter = _Waiter(dst, expected_opcode, key, akf, aid, fut)
        self._waiters.append(waiter)
        try:
            self._send_access_with_key(
                dst,
                payload,
                key=key,
                akf=akf,
                aid=aid,
            )
            return await asyncio.wait_for(fut, timeout)
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    async def request(
        self,
        dst: int,
        payload: bytes,
        expected_opcode: int,
        *,
        timeout: float = 5.0,
    ) -> ReceivedMessage:
        return await self._request_with_key(
            dst,
            payload,
            expected_opcode,
            key=self._appkey,
            akf=True,
            aid=self._aid,
            timeout=timeout,
        )

    async def request_devkey(
        self,
        dst: int,
        payload: bytes,
        expected_opcode: int,
        device_key: bytes,
        *,
        timeout: float = 8.0,
    ) -> ReceivedMessage:
        """Send an acknowledged Config Server request using DeviceKey."""
        if len(device_key) != 16:
            raise ValueError("device_key must be 16 bytes")

        return await self._request_with_key(
            dst,
            payload,
            expected_opcode,
            key=device_key,
            akf=False,
            aid=0,
            timeout=timeout,
        )
