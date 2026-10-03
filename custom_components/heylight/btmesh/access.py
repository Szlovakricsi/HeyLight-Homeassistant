"""Access-layer helpers for HeyLight vendor messages."""

from .errors import BtMeshError


class AccessError(BtMeshError):
    """Access PDU error."""


def encode_opcode(opcode: int) -> bytes:
    if 0 <= opcode <= 0x7E:
        return bytes([opcode])
    if 0x8000 <= opcode <= 0xBFFF:
        return opcode.to_bytes(2, "big")
    if 0xC00000 <= opcode <= 0xFFFFFF:
        return opcode.to_bytes(3, "big")
    raise AccessError(f"opcode not encodable: {opcode:#x}")


def parse_access(payload: bytes) -> tuple[int, bytes]:
    if not payload:
        raise AccessError("empty access payload")
    first = payload[0]
    if first == 0x7F:
        raise AccessError("reserved access opcode")
    size = 1 if first < 0x80 else 2 if first < 0xC0 else 3
    if len(payload) < size:
        raise AccessError("truncated access opcode")
    return int.from_bytes(payload[:size], "big"), payload[size:]


def vendor_opcode(op_byte: int, company_id: int) -> int:
    if not 0xC0 <= op_byte <= 0xFF:
        raise AccessError("vendor opcode byte out of range")
    return int.from_bytes(
        bytes([op_byte]) + company_id.to_bytes(2, "little"), "big"
    )
