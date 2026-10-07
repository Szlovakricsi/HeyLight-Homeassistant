"""Home Assistant Bluetooth helpers for HeyLight provisioning."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import HomeAssistant

from .btmesh.bearer import GattProvisioningBearer
from .btmesh.provisioning import MeshProvisioner, ProvisioningResult
from .const import (
    DEFAULT_SOURCE_ADDRESS,
    PROVISIONING_SERVICE,
)

SCAN_SECONDS = 8.0


@dataclass(frozen=True, slots=True)
class UnprovisionedDevice:
    """An unprovisioned Bluetooth Mesh device visible to Home Assistant."""

    address: str
    name: str
    rssi: int | None


def _supports_provisioning(info: BluetoothServiceInfoBleak) -> bool:
    uuids = {
        str(uuid).lower()
        for uuid in (getattr(info, "service_uuids", None) or ())
    }
    return (
        bool(getattr(info, "connectable", False))
        and PROVISIONING_SERVICE.lower() in uuids
    )


def _device_from_info(info: BluetoothServiceInfoBleak) -> UnprovisionedDevice:
    name = (
        str(getattr(info, "name", "") or "").strip()
        or str(getattr(info, "address", "") or "HeyLight")
    )
    rssi = getattr(info, "rssi", None)
    try:
        rssi = int(rssi) if rssi is not None else None
    except (TypeError, ValueError):
        rssi = None

    return UnprovisionedDevice(
        address=info.address,
        name=name,
        rssi=rssi,
    )


async def async_scan_unprovisioned(
    hass: HomeAssistant,
    *,
    duration: float = SCAN_SECONDS,
) -> list[UnprovisionedDevice]:
    """Actively scan for connectable devices exposing Mesh Provisioning."""
    found: dict[str, UnprovisionedDevice] = {}

    for info in bluetooth.async_discovered_service_info(
        hass, connectable=False
    ):
        if _supports_provisioning(info):
            found[info.address] = _device_from_info(info)

    def _callback(
        info: BluetoothServiceInfoBleak,
        _change: BluetoothChange,
    ) -> None:
        if _supports_provisioning(info):
            found[info.address] = _device_from_info(info)

    unregister = bluetooth.async_register_callback(
        hass,
        _callback,
        BluetoothCallbackMatcher(service_uuid=PROVISIONING_SERVICE),
        BluetoothScanningMode.ACTIVE,
    )
    try:
        await asyncio.sleep(max(1.0, float(duration)))
    finally:
        unregister()

    return sorted(
        found.values(),
        key=lambda device: (
            -(device.rssi if device.rssi is not None else -999),
            device.name.lower(),
            device.address,
        ),
    )


def _known_ranges(network) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for node in network.nodes:
        count = max(1, int(getattr(node, "element_count", 1)))
        ranges.append((node.unicast, node.unicast + count - 1))
    return ranges


def validate_unicast_address(
    network,
    address: int,
    element_count: int,
) -> int:
    """Validate that an address range does not overlap known nodes."""
    address = int(address)
    element_count = int(element_count)
    end = address + element_count - 1

    if element_count < 1:
        raise ValueError("element_count must be positive")
    if not 1 <= address < DEFAULT_SOURCE_ADDRESS:
        raise ValueError("unicast address must be in 0x0001..0x7FFE")
    if end >= DEFAULT_SOURCE_ADDRESS:
        raise ValueError(
            "device element range would collide with the provisioner address"
        )

    for used_start, used_end in _known_ranges(network):
        if address <= used_end and end >= used_start:
            raise ValueError(
                "requested unicast range overlaps a known mesh node"
            )

    return address


def next_unicast_address(network, element_count: int) -> int:
    """Allocate the next contiguous unicast range owned by this integration."""
    ranges = _known_ranges(network)
    candidate = max((end for _start, end in ranges), default=0) + 1
    return validate_unicast_address(network, candidate, element_count)


async def _async_connect_provisioning_bearer(
    hass: HomeAssistant,
    address: str,
):
    ble_device = bluetooth.async_ble_device_from_address(
        hass, address, connectable=True
    )
    if ble_device is None:
        raise ConnectionError(
            f"no connectable Bluetooth device for {address}"
        )

    client = await establish_connection(
        BleakClientWithServiceCache,
        ble_device,
        f"heylight-provision-{address}",
        max_attempts=4,
    )
    return client, GattProvisioningBearer(client)


async def async_provision_device(
    hass: HomeAssistant,
    *,
    address: str,
    net_key: bytes,
    iv_index: int,
    allocate_unicast: Callable[[int], int],
    on_data_ready: (
        Callable[[ProvisioningResult], Awaitable[None] | None] | None
    ) = None,
) -> ProvisioningResult:
    """Connect over PB-GATT and provision one selected device."""
    client = None
    bearer = None

    try:
        client, bearer = await _async_connect_provisioning_bearer(
            hass, address
        )
        await bearer.start()
        provisioner = MeshProvisioner(
            bearer,
            net_key=net_key,
            iv_index=iv_index,
            allocate_unicast=allocate_unicast,
            on_data_ready=on_data_ready,
        )
        return await provisioner.run()
    finally:
        if bearer is not None:
            try:
                await bearer.stop()
            except Exception:
                pass
        if client is not None:
            try:
                if getattr(client, "is_connected", False):
                    await client.disconnect()
            except Exception:
                pass
