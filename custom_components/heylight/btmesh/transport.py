"""Bluetooth Mesh access transport codec.

Derived from dasimon135/ha-bluetooth-mesh (MIT), copyright David Simon.
"""

from typing import NamedTuple

from cryptography.exceptions import InvalidTag

from .crypto import ccm_decrypt, ccm_encrypt
from .errors import BtMeshError

SEGMENT_SIZE = 12
UNSEG_MAX_UPPER_LEN = 15
TRANS_MIC_LEN = 4
MAX_SEGMENTS = 32

_APP_NONCE_TYPE = 0x01


class TransportError(BtMeshError):
    """Transport PDU error."""


class UnsegmentedAccess(NamedTuple):
    akf: bool
    aid: int
    upper_pdu: bytes


class AccessSegment(NamedTuple):
    akf: bool
    aid: int
    szmic: int
    seq_zero: int
    seg_o: int
    seg_n: int
    segment: bytes


def _access_nonce(
    akf: bool, seq: int, src: int, dst: int, iv_index: int
) -> bytes:
    # HeyLight only sends AppKey traffic. Keep the full AKF field for decoding.
    nonce_type = _APP_NONCE_TYPE if akf else 0x02
    return (
        bytes([nonce_type, 0x00])
        + seq.to_bytes(3, "big")
        + src.to_bytes(2, "big")
        + dst.to_bytes(2, "big")
        + iv_index.to_bytes(4, "big")
    )


def encrypt_access(
    key: bytes,
    *,
    akf: bool,
    seq: int,
    src: int,
    dst: int,
    iv_index: int,
    access_pdu: bytes,
) -> bytes:
    return ccm_encrypt(
        key,
        _access_nonce(akf, seq, src, dst, iv_index),
        access_pdu,
        TRANS_MIC_LEN,
    )


def decrypt_access(
    key: bytes,
    *,
    akf: bool,
    seq: int,
    src: int,
    dst: int,
    iv_index: int,
    upper_pdu: bytes,
) -> bytes:
    try:
        return ccm_decrypt(
            key,
            _access_nonce(akf, seq, src, dst, iv_index),
            upper_pdu,
            TRANS_MIC_LEN,
        )
    except (InvalidTag, ValueError) as exc:
        raise TransportError("upper transport authentication failed") from exc


def build_unsegmented_access(
    upper_pdu: bytes, *, akf: bool, aid: int
) -> bytes:
    if not 1 <= len(upper_pdu) <= UNSEG_MAX_UPPER_LEN:
        raise TransportError("invalid unsegmented upper PDU length")
    return bytes([(int(akf) << 6) | aid]) + upper_pdu


def segment_access_message(
    upper_pdu: bytes, *, akf: bool, aid: int, first_seq: int
) -> list[tuple[int, bytes]]:
    if not upper_pdu:
        raise TransportError("empty upper PDU")
    seg_count = (len(upper_pdu) + SEGMENT_SIZE - 1) // SEGMENT_SIZE
    if seg_count > MAX_SEGMENTS:
        raise TransportError("access message needs too many segments")

    seq_zero = first_seq & 0x1FFF
    seg_n = seg_count - 1
    octet0 = 0x80 | (int(akf) << 6) | aid
    result: list[tuple[int, bytes]] = []

    for seg_o in range(seg_count):
        header = (seq_zero << 10) | (seg_o << 5) | seg_n
        chunk = upper_pdu[
            seg_o * SEGMENT_SIZE : (seg_o + 1) * SEGMENT_SIZE
        ]
        result.append(
            (
                first_seq + seg_o,
                bytes([octet0]) + header.to_bytes(3, "big") + chunk,
            )
        )
    return result


def parse_access_lower(pdu: bytes) -> UnsegmentedAccess | AccessSegment:
    if not pdu:
        raise TransportError("empty lower transport PDU")
    seg = pdu[0] >> 7
    akf = bool((pdu[0] >> 6) & 1)
    aid = pdu[0] & 0x3F

    if not seg:
        if len(pdu) < 2:
            raise TransportError("unsegmented access message has no payload")
        return UnsegmentedAccess(akf, aid, pdu[1:])

    if len(pdu) < 5:
        raise TransportError("segmented access message truncated")

    header = int.from_bytes(pdu[1:4], "big")
    return AccessSegment(
        akf=akf,
        aid=aid,
        szmic=header >> 23,
        seq_zero=(header >> 10) & 0x1FFF,
        seg_o=(header >> 5) & 0x1F,
        seg_n=header & 0x1F,
        segment=pdu[4:],
    )
