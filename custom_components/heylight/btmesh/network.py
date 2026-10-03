"""Bluetooth Mesh network PDU codec.

Derived from dasimon135/ha-bluetooth-mesh (MIT), copyright David Simon.
"""

from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag

from .crypto import aes_ecb, ccm_decrypt, ccm_encrypt, k2
from .errors import BtMeshError


class NetworkError(BtMeshError):
    """Invalid or unauthenticated Mesh network PDU."""


@dataclass(frozen=True)
class DecodedNetworkPDU:
    ctl: bool
    ttl: int
    seq: int
    src: int
    dst: int
    transport_pdu: bytes


@dataclass
class NetworkContext:
    net_key: bytes
    iv_index: int
    seq: int = 0
    nid: int = field(init=False)
    encryption_key: bytes = field(init=False)
    privacy_key: bytes = field(init=False)

    def __post_init__(self) -> None:
        self.nid, self.encryption_key, self.privacy_key = k2(
            self.net_key, b"\x00"
        )

    def next_seq(self, count: int = 1) -> int:
        if count < 1:
            raise NetworkError("sequence allocation must be positive")
        if self.seq + count - 1 > 0xFFFFFF:
            raise NetworkError("Bluetooth Mesh sequence space exhausted")
        first = self.seq
        self.seq += count
        return first


def _network_nonce(
    ctl: bool, ttl: int, seq: int, src: int, iv_index: int
) -> bytes:
    return (
        bytes([0x00, (int(ctl) << 7) | ttl])
        + seq.to_bytes(3, "big")
        + src.to_bytes(2, "big")
        + b"\x00\x00"
        + iv_index.to_bytes(4, "big")
    )


def _pecb(privacy_key: bytes, iv_index: int, privacy_random: bytes) -> bytes:
    plain = bytes(5) + iv_index.to_bytes(4, "big") + privacy_random
    return aes_ecb(privacy_key, plain)[:6]


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def encode(
    ctx: NetworkContext,
    *,
    ctl: bool,
    ttl: int,
    seq: int,
    src: int,
    dst: int,
    transport_pdu: bytes,
) -> bytes:
    if not 0 <= ttl <= 0x7F:
        raise NetworkError("TTL out of range")
    if not transport_pdu:
        raise NetworkError("empty transport PDU")

    ivi = ctx.iv_index & 1
    header = (
        bytes([(int(ctl) << 7) | ttl])
        + seq.to_bytes(3, "big")
        + src.to_bytes(2, "big")
    )
    nonce = _network_nonce(ctl, ttl, seq, src, ctx.iv_index)
    mic_len = 8 if ctl else 4
    encrypted = ccm_encrypt(
        ctx.encryption_key,
        nonce,
        dst.to_bytes(2, "big") + transport_pdu,
        mic_len,
    )
    obfuscated = _xor(
        header, _pecb(ctx.privacy_key, ctx.iv_index, encrypted[:7])
    )
    return bytes([(ivi << 7) | ctx.nid]) + obfuscated + encrypted


def decode(ctx: NetworkContext, raw: bytes) -> DecodedNetworkPDU:
    if len(raw) < 14:
        raise NetworkError("network PDU too short")
    if raw[0] & 0x7F != ctx.nid:
        raise NetworkError("NID mismatch")
    if raw[0] >> 7 != (ctx.iv_index & 1):
        raise NetworkError("IVI mismatch")

    encrypted = raw[7:]
    header = _xor(
        raw[1:7], _pecb(ctx.privacy_key, ctx.iv_index, encrypted[:7])
    )
    ctl = bool(header[0] >> 7)
    ttl = header[0] & 0x7F
    seq = int.from_bytes(header[1:4], "big")
    src = int.from_bytes(header[4:6], "big")
    nonce = _network_nonce(ctl, ttl, seq, src, ctx.iv_index)
    mic_len = 8 if ctl else 4
    try:
        plaintext = ccm_decrypt(
            ctx.encryption_key, nonce, encrypted, mic_len
        )
    except (InvalidTag, ValueError) as exc:
        raise NetworkError("network PDU authentication failed") from exc

    if len(plaintext) < 3:
        raise NetworkError("network PDU has no transport payload")

    return DecodedNetworkPDU(
        ctl=ctl,
        ttl=ttl,
        seq=seq,
        src=src,
        dst=int.from_bytes(plaintext[:2], "big"),
        transport_pdu=plaintext[2:],
    )
