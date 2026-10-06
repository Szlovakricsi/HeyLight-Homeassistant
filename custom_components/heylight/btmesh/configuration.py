"""Bluetooth Mesh Configuration Client messages needed after provisioning."""

from __future__ import annotations

from .access import encode_opcode

_CONFIG_APPKEY_ADD = 0x00
_CONFIG_APPKEY_STATUS = 0x8003
_CONFIG_MODEL_APP_BIND = 0x803D
_CONFIG_MODEL_APP_STATUS = 0x803E

_STATUS_SUCCESS = 0x00


class MeshConfigurationError(Exception):
    """A Config Server operation failed."""


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
    return company_id.to_bytes(2, "little") + model_id.to_bytes(2, "little")


def _check_status(params: bytes, operation: str) -> None:
    if not params:
        raise MeshConfigurationError(f"{operation} returned no status")
    if params[0] != _STATUS_SUCCESS:
        raise MeshConfigurationError(
            f"{operation} failed with status 0x{params[0]:02X}"
        )


async def async_add_app_key(
    controller,
    *,
    unicast: int,
    device_key: bytes,
    app_key: bytes,
    net_key_index: int = 0,
    app_key_index: int = 0,
) -> None:
    """Install the existing network AppKey on a newly provisioned node."""
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
        timeout=10.0,
    )
    _check_status(msg.params, "Config AppKey Add")


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
        timeout=8.0,
    )
    _check_status(msg.params, "Config Model App Bind")
