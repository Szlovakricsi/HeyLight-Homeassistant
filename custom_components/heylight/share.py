"""Parser for Heylight 'Share Device' QR payloads."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from .btmesh.crypto import k3
from .const import HEYLIGHT_COMPANY_ID, HEYLIGHT_VENDOR_MODEL


class ShareDataError(ValueError):
    """The QR payload is not a supported Heylight Share Device export."""


@dataclass(frozen=True)
class MeshElement:
    index: int
    location: int
    models: tuple[int, ...]


@dataclass(frozen=True)
class HeylightNode:
    name: str
    mac: str
    unicast: int
    device_key: bytes
    cid: int
    pid: int
    vid: int
    crpl: int
    features: int
    elements: tuple[MeshElement, ...]
    product_type: int
    bulb_count: int
    frequency: int
    output: int

    @property
    def firmware_label(self) -> str:
        raw = self.vid.to_bytes(2, "little")
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError:
            return f"0x{self.vid:04X}"
        return text if text.isprintable() else f"0x{self.vid:04X}"

    def has_model(self, model_id: int) -> bool:
        return any(model_id in element.models for element in self.elements)


@dataclass(frozen=True)
class HeylightNetwork:
    agent: str
    mesh_name: str
    mesh_password: str
    nodes: tuple[HeylightNode, ...]
    sno: int

    @property
    def net_key(self) -> bytes:
        return self.mesh_password.encode("ascii")

    @property
    def app_key(self) -> bytes:
        return self.mesh_name.encode("ascii")

    @property
    def network_id(self) -> bytes:
        return k3(self.net_key)

    @property
    def identifier(self) -> str:
        return self.network_id.hex()

    @property
    def proxy_macs(self) -> frozenset[str]:
        return frozenset(node.mac.upper() for node in self.nodes)


_MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ShareDataError(f"missing or invalid '{key}'")
    return value


def _parse_composition(info_hex: str) -> tuple[
    int, int, int, int, int, tuple[MeshElement, ...]
]:
    try:
        raw = bytes.fromhex(info_hex)
    except ValueError as exc:
        raise ShareDataError("node 'i' is not hexadecimal") from exc

    if len(raw) < 32:
        raise ShareDataError("node 'i' is too short")

    comp_len = int.from_bytes(raw[20:22], "little")
    comp = raw[22 : 22 + comp_len]
    if len(comp) != comp_len or len(comp) < 10:
        raise ShareDataError("node composition data is truncated")

    cid = int.from_bytes(comp[0:2], "little")
    pid = int.from_bytes(comp[2:4], "little")
    vid = int.from_bytes(comp[4:6], "little")
    crpl = int.from_bytes(comp[6:8], "little")
    features = int.from_bytes(comp[8:10], "little")

    offset = 10
    elements: list[MeshElement] = []
    index = 0
    while offset < len(comp):
        if offset + 4 > len(comp):
            raise ShareDataError("truncated element header")
        location = int.from_bytes(comp[offset : offset + 2], "little")
        num_sig = comp[offset + 2]
        num_vendor = comp[offset + 3]
        offset += 4

        models: list[int] = []
        need = num_sig * 2 + num_vendor * 4
        if offset + need > len(comp):
            raise ShareDataError("truncated model list")

        for _ in range(num_sig):
            models.append(
                int.from_bytes(comp[offset : offset + 2], "little")
            )
            offset += 2

        for _ in range(num_vendor):
            vendor_cid = int.from_bytes(
                comp[offset : offset + 2], "little"
            )
            model_id = int.from_bytes(
                comp[offset + 2 : offset + 4], "little"
            )
            models.append((vendor_cid << 16) | model_id)
            offset += 4

        elements.append(
            MeshElement(index=index, location=location, models=tuple(models))
        )
        index += 1

    if not elements:
        raise ShareDataError("composition contains no elements")

    return cid, pid, vid, crpl, features, tuple(elements)


def parse_share_text(text: str) -> HeylightNetwork:
    """Parse decoded QR text into a validated network."""
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ShareDataError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ShareDataError("QR payload must be a JSON object")

    mesh_name = _require_string(data, "meshName")
    mesh_pwd = _require_string(data, "meshPwd")
    if len(mesh_name.encode("ascii", errors="ignore")) != 16:
        raise ShareDataError("meshName must be exactly 16 ASCII bytes")
    if len(mesh_pwd.encode("ascii", errors="ignore")) != 16:
        raise ShareDataError("meshPwd must be exactly 16 ASCII bytes")
    try:
        mesh_name.encode("ascii")
        mesh_pwd.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ShareDataError("meshName/meshPwd must be ASCII") from exc

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ShareDataError("QR payload contains no nodes")

    nodes: list[HeylightNode] = []
    for item in raw_nodes:
        if not isinstance(item, dict):
            raise ShareDataError("invalid node entry")

        name = str(item.get("n") or "HeyLight")
        mac = _require_string(item, "m").upper()
        if not _MAC_RE.match(mac):
            raise ShareDataError(f"invalid Bluetooth address: {mac}")

        try:
            unicast = int(item["a"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ShareDataError("node has invalid unicast address") from exc
        if not 1 <= unicast <= 0x7FFF:
            raise ShareDataError("node unicast address is outside 0x0001..0x7FFF")

        key_text = _require_string(item, "k")
        try:
            device_key = bytes.fromhex(key_text)
        except ValueError as exc:
            raise ShareDataError("node device key is not hexadecimal") from exc
        if len(device_key) != 16:
            raise ShareDataError("node device key must be 16 bytes")

        info_hex = _require_string(item, "i")
        cid, pid, vid, crpl, features, elements = _parse_composition(info_hex)

        try:
            product_type = int(item.get("t", pid))
        except (TypeError, ValueError):
            product_type = pid

        product = item.get("p") if isinstance(item.get("p"), dict) else {}
        nodes.append(
            HeylightNode(
                name=name,
                mac=mac,
                unicast=unicast,
                device_key=device_key,
                cid=cid,
                pid=pid,
                vid=vid,
                crpl=crpl,
                features=features,
                elements=elements,
                product_type=product_type,
                bulb_count=int(product.get("l", 200) or 200),
                frequency=int(product.get("f", 0) or 0),
                output=int(product.get("o", 0) or 0),
            )
        )

    supported = [
        node
        for node in nodes
        if node.cid == HEYLIGHT_COMPANY_ID
        and node.has_model(HEYLIGHT_VENDOR_MODEL)
    ]
    if not supported:
        raise ShareDataError(
            "no supported Telink/Heylight vendor model 0x0211:0x0000 found"
        )

    return HeylightNetwork(
        agent=str(data.get("agent") or ""),
        mesh_name=mesh_name,
        mesh_password=mesh_pwd,
        nodes=tuple(nodes),
        sno=int(data.get("sno", 0) or 0),
    )


def normalize_share_text(text: str) -> str:
    """Return compact JSON after validation, without changing any key values."""
    parse_share_text(text)
    return json.dumps(
        json.loads(text.strip()),
        separators=(",", ":"),
        ensure_ascii=False,
    )
