"""Bluetooth Mesh Configuration Client helpers for newly provisioned nodes."""

from __future__ import annotations

from dataclasses import dataclass

from ..const import HEYLIGHT_VENDOR_MODEL
from .access import encode_opcode

_CONFIG_APPKEY_ADD = 0x00
_CONFIG_COMPOSITION_DATA_STATUS = 0x02
_CONFIG_APPKEY_STATUS = 0x8003
_CONFIG_COMPOSITION_DATA_GET = 0x8008
_CONFIG_MODEL_APP_BIND = 0x803D
_CONFIG_MODEL_APP_STATUS = 0x803E

_STATUS_SUCCESS = 0x00
_STATUS_KEY_INDEX_ALREADY_STORED = 0x06

# Models used by the current HeyLight integration.
_APPLICATION_MODELS = frozenset(
    {
        HEYLIGHT_VENDOR_MODEL,
        0x1200,  # Time Server
        0x1201,  # Time Setup Server
        0x1206,  # Scheduler Server
        0x1207,  # Scheduler Setup Server
    }
)


class MeshConfigurationError(Exception):
    """A Config Server operation failed."""


@dataclass(frozen=True, slots=True)
class CompositionElement:
    """One element from Composition Data Page 0."""

    index: int
    location: int
    models: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CompositionData:
    """Decoded Composition Data Page 0."""

    cid: int
    pid: int
    vid: int
    crpl: int
    features: int
    elements: tuple[CompositionElement, ...]


def parse_composition_page0(data: bytes) -> CompositionData:
    """Decode Composition Data Page 0."""
    if len(data) < 10:
        raise MeshConfigurationError("Composition Data Page 0 is truncated")

    cid = int.from_bytes(data[0:2], "little")
    pid = int.from_bytes(data[2:4], "little")
    vid = int.from_bytes(data[4:6], "little")
    crpl = int.from_bytes(data[6:8], "little")
    features = int.from_bytes(data[8:10], "little")

    offset = 10
    elements: list[CompositionElement] = []
    index = 0

    while offset < len(data):
        if offset + 4 > len(data):
            raise MeshConfigurationError(
                "Composition Data element header is truncated"
            )

        location = int.from_bytes(data[offset : offset + 2], "little")
        num_sig = data[offset + 2]
        num_vendor = data[offset + 3]
        offset += 4

        required = num_sig * 2 + num_vendor * 4
        if offset + required > len(data):
            raise MeshConfigurationError(
                "Composition Data model list is truncated"
            )

        models: list[int] = []
        for _ in range(num_sig):
            models.append(
                int.from_bytes(data[offset : offset + 2], "little")
            )
            offset += 2

        for _ in range(num_vendor):
            company_id = int.from_bytes(
                data[offset : offset + 2], "little"
            )
            model_id = int.from_bytes(
                data[offset + 2 : offset + 4], "little"
            )
            models.append((company_id << 16) | model_id)
            offset += 4

        elements.append(
            CompositionElement(
                index=index,
                location=location,
                models=tuple(models),
            )
        )
        index += 1

    if not elements:
        raise MeshConfigurationError("Composition Data contains no elements")

    return CompositionData(
        cid=cid,
        pid=pid,
        vid=vid,
        crpl=crpl,
        features=features,
        elements=tuple(elements),
    )


def _packed_key_indexes(net_key_index: int, app_key_index: int) -> bytes:
    if not 0 <= net_key_index <= 0xFFF:
        raise ValueError("NetKey index must be 0..4095")
    if not 0 <= app_key_index <= 0xFFF:
        raise ValueError("AppKey index must be 0..4095")

    packed = (net_key_index & 0xFFF) | ((app_key_index & 0xFFF) << 12)
    return packed.to_bytes(3, "little")


def _model_identifier(model: int) -> bytes:
    if 0 <= model <= 0xFFFF:
        return model.to_bytes(2, "little")

    company_id = (model >> 16) & 0xFFFF
    model_id = model & 0xFFFF
    return (
        company_id.to_bytes(2, "little")
        + model_id.to_bytes(2, "little")
    )


def _check_status(
    params: bytes,
    operation: str,
    *,
    accepted: frozenset[int] = frozenset({_STATUS_SUCCESS}),
) -> None:
    if not params:
        raise MeshConfigurationError(f"{operation} returned no status")
    if params[0] not in accepted:
        raise MeshConfigurationError(
            f"{operation} failed with status 0x{params[0]:02X}"
        )


async def async_get_composition(
    controller,
    *,
    unicast: int,
    device_key: bytes,
) -> CompositionData:
    """Read Composition Data Page 0 using the node DeviceKey."""
    payload = encode_opcode(_CONFIG_COMPOSITION_DATA_GET) + b"\x00"
    msg = await controller._node.request_devkey(
        unicast,
        payload,
        _CONFIG_COMPOSITION_DATA_STATUS,
        device_key,
        timeout=15.0,
    )

    if not msg.params:
        raise MeshConfigurationError(
            "Config Composition Data Status contained no page"
        )
    if msg.params[0] != 0:
        raise MeshConfigurationError(
            f"device returned Composition Data page {msg.params[0]}, "
            "expected page 0"
        )

    return parse_composition_page0(msg.params[1:])


async def async_add_app_key(
    controller,
    *,
    unicast: int,
    device_key: bytes,
    app_key: bytes,
    net_key_index: int = 0,
    app_key_index: int = 0,
) -> None:
    """Install the network AppKey on a newly provisioned node."""
    if len(app_key) != 16:
        raise ValueError("app_key must be 16 bytes")

    payload = (
        encode_opcode(_CONFIG_APPKEY_ADD)
        + _packed_key_indexes(net_key_index, app_key_index)
        + app_key
    )
    msg = await controller._node.request_devkey(
        unicast,
        payload,
        _CONFIG_APPKEY_STATUS,
        device_key,
        timeout=12.0,
    )
    _check_status(
        msg.params,
        "Config AppKey Add",
        accepted=frozenset(
            {_STATUS_SUCCESS, _STATUS_KEY_INDEX_ALREADY_STORED}
        ),
    )


async def async_bind_model(
    controller,
    *,
    node_unicast: int,
    element_address: int,
    model: int,
    device_key: bytes,
    app_key_index: int = 0,
) -> None:
    """Bind AppKey index 0 to one SIG or vendor model."""
    payload = (
        encode_opcode(_CONFIG_MODEL_APP_BIND)
        + int(element_address).to_bytes(2, "little")
        + int(app_key_index).to_bytes(2, "little")
        + _model_identifier(model)
    )
    msg = await controller._node.request_devkey(
        node_unicast,
        payload,
        _CONFIG_MODEL_APP_STATUS,
        device_key,
        timeout=10.0,
    )
    _check_status(msg.params, "Config Model App Bind")


async def async_configure_node(
    controller,
    *,
    unicast: int,
    device_key: bytes,
    app_key: bytes,
) -> CompositionData:
    """Read composition, install AppKey and bind the models we use."""
    composition = await async_get_composition(
        controller,
        unicast=unicast,
        device_key=device_key,
    )

    await async_add_app_key(
        controller,
        unicast=unicast,
        device_key=device_key,
        app_key=app_key,
    )

    for element in composition.elements:
        element_address = unicast + element.index
        for model in element.models:
            if model not in _APPLICATION_MODELS:
                continue
            await async_bind_model(
                controller,
                node_unicast=unicast,
                element_address=element_address,
                model=model,
                device_key=device_key,
            )

    if not any(
        HEYLIGHT_VENDOR_MODEL in element.models
        for element in composition.elements
    ):
        raise MeshConfigurationError(
            "the provisioned device does not expose the supported "
            "HeyLight/Telink vendor model"
        )

    return composition
