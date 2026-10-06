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


class _Waiter(NamedTuple):
    dst: int
    expected_opcode: int
    key: bytes
    akf: bool
    aid: int
    future: asyncio.Future[ReceivedMessage]


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
        """Send a Configuration message encrypted with a node DeviceKey."""
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

    def _dispatch(self, msg: ReceivedMessage, *, akf: bool) -> None:
        for waiter in tuple(self._waiters):
            if (
                waiter.dst == msg.src
                and waiter.expected_opcode == msg.opcode
                and waiter.akf == akf
                and not waiter.future.done()
            ):
                waiter.future.set_result(msg)
                break

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

        # Status responses used by this integration are unsegmented. Outbound
        # Config AppKey Add can be segmented, but its response is short.
        if not isinstance(lower, UnsegmentedAccess):
            return

        if lower.akf:
            if lower.aid != self._aid:
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
            self._dispatch(
                ReceivedMessage(pdu.src, opcode, params), akf=True
            )
            return

        if lower.aid != 0:
            return

        # DeviceKey traffic has no AID. Try only the DeviceKeys attached to
        # pending requests from this source so unrelated Config traffic is not
        # brute-forced against every known key.
        for waiter in tuple(self._waiters):
            if waiter.akf or waiter.dst != pdu.src:
                continue
            try:
                access_payload = decrypt_access(
                    waiter.key,
                    akf=False,
                    seq=pdu.seq,
                    src=pdu.src,
                    dst=pdu.dst,
                    iv_index=self._iv_index,
                    upper_pdu=lower.upper_pdu,
                )
                opcode, params = parse_access(access_payload)
            except Exception:
                continue
            if opcode != waiter.expected_opcode:
                continue
            if not waiter.future.done():
                waiter.future.set_result(
                    ReceivedMessage(pdu.src, opcode, params)
                )
            break

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
