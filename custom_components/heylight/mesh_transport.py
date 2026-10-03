"""Home Assistant Bluetooth bridge for the HeyLight Mesh Proxy."""

from __future__ import annotations

import logging
from collections.abc import Callable

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import HomeAssistant

from .btmesh.bearer import GattProxyBearer
from .const import PROXY_SERVICE

_LOGGER = logging.getLogger(__name__)

IDENTIFICATION_NETWORK_ID = 0x00
IDENTIFICATION_NODE_IDENTITY = 0x01


class MeshTransportError(Exception):
    """A matching HeyLight Mesh Proxy could not be connected."""


def parse_proxy_service_data(data: bytes) -> tuple[int, bytes] | None:
    if not data:
        return None
    id_type = data[0]
    parameter = data[1:]
    if id_type == IDENTIFICATION_NETWORK_ID and len(parameter) == 8:
        return id_type, parameter
    if id_type == IDENTIFICATION_NODE_IDENTITY and len(parameter) == 16:
        return id_type, parameter
    return None


def _matches(
    info: BluetoothServiceInfoBleak,
    network_id: bytes,
    proxy_macs: frozenset[str],
) -> bool:
    data = info.service_data.get(PROXY_SERVICE)
    if data is None:
        return False

    parsed = parse_proxy_service_data(bytes(data))
    if parsed is None:
        return False

    id_type, parameter = parsed
    if id_type == IDENTIFICATION_NETWORK_ID:
        return parameter == network_id

    # HeyLight's tested Telink firmware advertises Node Identity instead of
    # Network ID after provisioning. The Share Device QR contains the device
    # Bluetooth address, so use that address as the network-scoped identity
    # rather than accepting arbitrary Node Identity advertisements.
    return info.address.upper() in proxy_macs


def find_proxy_address(
    hass: HomeAssistant,
    network_id: bytes,
    proxy_macs: frozenset[str],
) -> str | None:
    for info in bluetooth.async_discovered_service_info(
        hass, connectable=False
    ):
        if not getattr(info, "connectable", False):
            continue
        if _matches(info, network_id, proxy_macs):
            return info.address
    return None


def async_register_proxy_callback(
    hass: HomeAssistant,
    network_id: bytes,
    proxy_macs: frozenset[str],
    on_found: Callable[[str], None],
) -> Callable[[], None]:
    def _callback(
        info: BluetoothServiceInfoBleak, _change: BluetoothChange
    ) -> None:
        if _matches(info, network_id, proxy_macs):
            on_found(info.address)

    return bluetooth.async_register_callback(
        hass,
        _callback,
        BluetoothCallbackMatcher(service_uuid=PROXY_SERVICE),
        BluetoothScanningMode.ACTIVE,
    )


async def async_connect_bearer(
    hass: HomeAssistant, address: str
) -> tuple[object, GattProxyBearer]:
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    if ble_device is None:
        raise MeshTransportError(
            f"no connectable Bluetooth device for {address}"
        )

    try:
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            f"heylight-{address}",
            max_attempts=4,
        )
    except Exception as exc:
        raise MeshTransportError(
            f"could not connect to HeyLight proxy {address}: {exc}"
        ) from exc

    return client, GattProxyBearer(client)
