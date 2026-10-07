"""Parser and storage helpers for HeyLight mesh network data."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import secrets
from typing import Any

from .btmesh.crypto import k3
from .const import HEYLIGHT_COMPANY_ID, HEYLIGHT_VENDOR_MODEL


class ShareDataError(ValueError):
    """The stored/imported HeyLight mesh payload is not supported."""


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
    element_count: int = 1
    configured: bool = True

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
    managed: bool = False
    display_name: str = ""
    iv_index: int = 0
    _net_key: bytes | None = None
    _app_key: bytes | None = None

    @property
    def net_key(self) -> bytes:
        if self._net_key is not None:
            return self._net_key
        return self.mesh_password.encode("ascii")

    @property
    def app_key(self) -> bytes:
        if self._app_key is not None:
            return self._app_key
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

    @property
    def title(self) -> str:
        return self.display_name or self.mesh_name


_MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ShareDataError(f"missing or invalid '{key}'")
    return value


def _parse_key_hex(data: dict[str, Any], key: str) -> bytes:
    text = _require_string(data, key)
    try:
        value = bytes.fromhex(text)
    except ValueError as exc:
        raise ShareDataError(f"'{key}' is not hexadecimal") from exc
    if len(value) != 16:
        raise ShareDataError(f"'{key}' must be 16 bytes")
    return value


def _parse_composition_bytes(
    comp: bytes,
) -> tuple[int, int, int, int, int, tuple[MeshElement, ...]]:
    if len(comp) < 10:
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


def _parse_legacy_composition(info_hex: str) -> tuple[
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
    if len(comp) != comp_len:
        raise ShareDataError("node composition data is truncated")

    return _parse_composition_bytes(comp)


def _parse_stored_composition(value: Any) -> tuple[
    int, int, int, int, int, tuple[MeshElement, ...]
]:
    if not isinstance(value, dict):
        raise ShareDataError("node composition must be an object")

    try:
        cid = int(value["cid"])
        pid = int(value["pid"])
        vid = int(value["vid"])
        crpl = int(value["crpl"])
        features = int(value["features"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ShareDataError("node composition header is invalid") from exc

    raw_elements = value.get("elements")
    if not isinstance(raw_elements, list) or not raw_elements:
        raise ShareDataError("node composition contains no elements")

    elements: list[MeshElement] = []
    for index, raw in enumerate(raw_elements):
        if not isinstance(raw, dict):
            raise ShareDataError("node composition element is invalid")
        try:
            location = int(raw.get("location", 0))
            models = tuple(int(model) for model in raw["models"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ShareDataError(
                "node composition model list is invalid"
            ) from exc
        elements.append(
            MeshElement(index=index, location=location, models=models)
        )

    return cid, pid, vid, crpl, features, tuple(elements)


def _parse_node(item: dict[str, Any]) -> HeylightNode:
    name = str(item.get("n") or "HeyLight")
    mac = _require_string(item, "m").upper()
    if not _MAC_RE.match(mac):
        raise ShareDataError(f"invalid Bluetooth address: {mac}")

    try:
        unicast = int(item["a"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ShareDataError("node has invalid unicast address") from exc
    if not 1 <= unicast <= 0x7FFF:
        raise ShareDataError(
            "node unicast address is outside 0x0001..0x7FFF"
        )

    key_text = _require_string(item, "k")
    try:
        device_key = bytes.fromhex(key_text)
    except ValueError as exc:
        raise ShareDataError("node device key is not hexadecimal") from exc
    if len(device_key) != 16:
        raise ShareDataError("node device key must be 16 bytes")

    configured = bool(item.get("configured", True))
    try:
        element_count = max(1, int(item.get("elementCount", 1)))
    except (TypeError, ValueError) as exc:
        raise ShareDataError("node element count is invalid") from exc

    cid = pid = vid = crpl = features = 0
    elements: tuple[MeshElement, ...] = ()

    if isinstance(item.get("i"), str):
        cid, pid, vid, crpl, features, elements = (
            _parse_legacy_composition(item["i"])
        )
        element_count = len(elements)
    elif item.get("composition") is not None:
        cid, pid, vid, crpl, features, elements = (
            _parse_stored_composition(item["composition"])
        )
        element_count = len(elements)
    elif configured:
        raise ShareDataError(
            "configured node is missing composition data"
        )

    try:
        product_type = int(item.get("t", pid))
    except (TypeError, ValueError):
        product_type = pid

    product = item.get("p") if isinstance(item.get("p"), dict) else {}
    return HeylightNode(
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
        element_count=element_count,
        configured=configured,
    )


def parse_share_text(text: str) -> HeylightNetwork:
    """Parse imported or integration-managed mesh data."""
    try:
        data = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ShareDataError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ShareDataError("mesh payload must be a JSON object")

    managed = bool(data.get("managed", False))
    mesh_name = _require_string(data, "meshName")
    mesh_pwd = _require_string(data, "meshPwd")

    for key, value in (("meshName", mesh_name), ("meshPwd", mesh_pwd)):
        try:
            encoded = value.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ShareDataError(f"{key} must be ASCII") from exc
        if len(encoded) != 16:
            raise ShareDataError(
                f"{key} must be exactly 16 ASCII bytes"
            )

    net_key = app_key = None
    if managed:
        net_key = _parse_key_hex(data, "netKey")
        app_key = _parse_key_hex(data, "appKey")

    try:
        iv_index = int(data.get("ivIndex", 0))
    except (TypeError, ValueError) as exc:
        raise ShareDataError("ivIndex is invalid") from exc
    if not 0 <= iv_index <= 0xFFFFFFFF:
        raise ShareDataError("ivIndex must fit in 32 bits")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ShareDataError("mesh payload has an invalid nodes list")
    if not raw_nodes and not managed:
        raise ShareDataError("QR payload contains no nodes")

    nodes: list[HeylightNode] = []
    seen_addresses: set[int] = set()
    for item in raw_nodes:
        if not isinstance(item, dict):
            raise ShareDataError("invalid node entry")
        node = _parse_node(item)

        occupied = range(
            node.unicast,
            node.unicast + max(1, node.element_count),
        )
        if any(address in seen_addresses for address in occupied):
            raise ShareDataError("node unicast address ranges overlap")
        seen_addresses.update(occupied)
        nodes.append(node)

    supported = [
        node
        for node in nodes
        if node.configured
        and node.cid == HEYLIGHT_COMPANY_ID
        and node.has_model(HEYLIGHT_VENDOR_MODEL)
    ]
    if not managed and not supported:
        raise ShareDataError(
            "no supported Telink/Heylight vendor model 0x0211:0x0000 found"
        )

    return HeylightNetwork(
        agent=str(data.get("agent") or ""),
        mesh_name=mesh_name,
        mesh_password=mesh_pwd,
        nodes=tuple(nodes),
        sno=int(data.get("sno", 0) or 0),
        managed=managed,
        display_name=str(data.get("displayName") or ""),
        iv_index=iv_index,
        _net_key=net_key,
        _app_key=app_key,
    )


def normalize_share_text(text: str) -> str:
    """Return compact JSON after validation, without changing key values."""
    parse_share_text(text)
    return json.dumps(
        json.loads(text.strip()),
        separators=(",", ":"),
        ensure_ascii=False,
    )


def create_managed_share_text(display_name: str) -> str:
    """Create persistent data for a new integration-owned mesh network."""
    name = str(display_name).strip() or "HeyLight Mesh"
    data = {
        "agent": "Home Assistant",
        "managed": True,
        "schemaVersion": 1,
        "displayName": name,
        # Keep the legacy 16-byte fields so exported/debug data remains easy
        # to recognize, while the actual managed network keys are full random
        # 128-bit values stored below.
        "meshName": secrets.token_hex(8),
        "meshPwd": secrets.token_hex(8),
        "netKey": secrets.token_hex(16),
        "appKey": secrets.token_hex(16),
        "ivIndex": 0,
        "nodes": [],
        "sno": 0,
    }
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    parse_share_text(text)
    return text


def append_provisioned_node(
    text: str,
    *,
    name: str,
    mac: str,
    unicast: int,
    device_key: bytes,
    element_count: int,
) -> str:
    """Persist a provisioned node before Config Server setup is complete."""
    network = parse_share_text(text)
    if any(node.mac.upper() == mac.upper() for node in network.nodes):
        raise ShareDataError("this Bluetooth device is already stored")

    data = json.loads(text)
    data["nodes"].append(
        {
            "n": str(name).strip() or "HeyLight",
            "m": mac.upper(),
            "a": int(unicast),
            "k": bytes(device_key).hex(),
            "configured": False,
            "elementCount": int(element_count),
            "managedByHomeAssistant": True,
            "t": 0,
            "p": {"l": 200, "f": 0, "o": 0},
        }
    )
    data["sno"] = int(data.get("sno", 0) or 0) + 1

    result = json.dumps(
        data, separators=(",", ":"), ensure_ascii=False
    )
    parse_share_text(result)
    return result


def finalize_provisioned_node(
    text: str,
    *,
    unicast: int,
    composition,
) -> str:
    """Store Composition Data and mark a provisioned node ready for entities."""
    data = json.loads(text)
    target = None
    for item in data.get("nodes", []):
        if int(item.get("a", -1)) == int(unicast):
            target = item
            break
    if target is None:
        raise ShareDataError(
            f"provisioned node 0x{int(unicast):04X} is not stored"
        )

    target["composition"] = {
        "cid": int(composition.cid),
        "pid": int(composition.pid),
        "vid": int(composition.vid),
        "crpl": int(composition.crpl),
        "features": int(composition.features),
        "elements": [
            {
                "location": int(element.location),
                "models": [int(model) for model in element.models],
            }
            for element in composition.elements
        ],
    }
    target["configured"] = True
    target["elementCount"] = len(composition.elements)
    target["t"] = int(composition.pid)
    data["sno"] = int(data.get("sno", 0) or 0) + 1

    result = json.dumps(
        data, separators=(",", ":"), ensure_ascii=False
    )
    parse_share_text(result)
    return result
