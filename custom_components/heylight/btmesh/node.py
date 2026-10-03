"""Small provisioner-side Mesh node used by HeyLight."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import NamedTuple

from . import network
from .access import parse_access
from .crypto import k4
from .network import NetworkContext, NetworkError
from .transport import (
    TRANS_MIC_LEN,
    UNSEG_MAX_UPPER_LEN,
    UnsegmentedAccess,
    build_unsegmented_access,
    decrypt_access,
    encrypt_access,
    parse_access_lower,
    segment_access_message,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_TTL = 7


class ReceivedMessage(NamedTuple):
    src: int
    opcode: int
    params: bytes


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
        self._waiters: list[
            tuple[int, int, asyncio.Future[ReceivedMessage]]
        ] = []

    def send_access(
        self, dst: int, payload: bytes, *, ttl: int = DEFAULT_TTL
    ) -> None:
        upper_len = len(payload) + TRANS_MIC_LEN

        if upper_len <= UNSEG_MAX_UPPER_LEN:
            seq = self.ctx.next_seq()
            upper = encrypt_access(
                self._appkey,
                akf=True,
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
                        upper, akf=True, aid=self._aid
                    ),
                )
            ]
        else:
            seg_count = (upper_len + 11) // 12
            first_seq = self.ctx.next_seq(seg_count)
            upper = encrypt_access(
                self._appkey,
                akf=True,
                seq=first_seq,
                src=self._src,
                dst=dst,
                iv_index=self._iv_index,
                access_pdu=payload,
            )
            pdus = segment_access_message(
                upper,
                akf=True,
                aid=self._aid,
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

        # HeyLight power Status is unsegmented. Scene commands are
        # unacknowledged, so no segmented inbound Access message is required.
        if not isinstance(lower, UnsegmentedAccess):
            return
        if not lower.akf or lower.aid != self._aid:
            return

        try:
            access_payload = decrypt_access(
                self._appkey,
                akf=True,
                seq=pdu.seq,
                src=pdu.src,
                dst=pdu.dst,
                iv_index=self._iv_index,
                upper_pdu=lower.upper_pdu,
            )
            opcode, params = parse_access(access_payload)
        except Exception:
            return

        msg = ReceivedMessage(pdu.src, opcode, params)
        for dst, expected, fut in tuple(self._waiters):
            if (
                dst == msg.src
                and expected == msg.opcode
                and not fut.done()
            ):
                fut.set_result(msg)
                break

    async def request(
        self,
        dst: int,
        payload: bytes,
        expected_opcode: int,
        *,
        timeout: float = 5.0,
    ) -> ReceivedMessage:
        fut: asyncio.Future[ReceivedMessage] = (
            asyncio.get_running_loop().create_future()
        )
        waiter = (dst, expected_opcode, fut)
        self._waiters.append(waiter)
        try:
            self.send_access(dst, payload)
            return await asyncio.wait_for(fut, timeout)
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)
