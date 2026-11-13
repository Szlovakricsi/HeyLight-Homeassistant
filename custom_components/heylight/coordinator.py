"""Connection lifecycle and command serialization for HeyLight."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from time import monotonic
from collections.abc import Callable

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .btmesh.controller import HeylightMeshController
from .const import DEFAULT_SOURCE_ADDRESS
from .mesh_transport import (
    async_connect_bearer,
    async_register_proxy_callback,
    find_proxy_address,
    find_proxy_service_info,
)
from .share import HeylightNetwork

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
SEQ_SAFETY_MARGIN = 32
RECONNECT_SECONDS = 5
RSSI_STALE_SECONDS = 120
RSSI_REPORT_INTERVAL_SECONDS = 10


class HeylightCoordinator:
    """One runtime per HeyLight mesh network."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        network: HeylightNetwork,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.network = network

        self.available = False
        self.connected_address: str | None = None

        self._client: Any | None = None
        self._controller: HeylightMeshController | None = None
        self._listeners: list[Callable[[], None]] = []
        self._rssi_listeners: list[Callable[[], None]] = []
        self.rssi_address: str | None = None
        self.rssi_source: str | None = None
        self.last_rssi_dbm: int | None = None
        self._rssi_seen_monotonic: float | None = None
        self._rssi_seen_at: datetime | None = None
        self._rssi_last_published: float | None = None
        self._rssi_fresh = False
        self._connect_lock = asyncio.Lock()
        self._disconnect_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._background_task: asyncio.Task | None = None
        self._unregister_bluetooth: Callable[[], None] | None = None
        self._stopping = False
        self._provisioning = False
        self.reconnect_attempts = 0
        self.manual_reconnect_requests = 0
        self.successful_connections = 0
        self.last_connection_error: str | None = None
        self.last_disconnect_reason: str | None = None

        self._store: Store = Store(
            hass, STORE_VERSION, f"heylight_seq_{entry_id}"
        )
        self._seq = 0

    def _register_proxy_callback(self) -> None:
        if self._unregister_bluetooth is not None:
            self._unregister_bluetooth()
            self._unregister_bluetooth = None

        self._unregister_bluetooth = async_register_proxy_callback(
            self.hass,
            self.network.network_id,
            self.network.net_key,
            tuple(node.unicast for node in self.network.nodes),
            self.network.proxy_macs,
            self._proxy_seen,
        )
        known = find_proxy_service_info(
            self.hass,
            self.network.network_id,
            self.network.net_key,
            tuple(node.unicast for node in self.network.nodes),
            self.network.proxy_macs,
        )
        if known is not None:
            self._record_proxy_rssi(known)

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        try:
            saved = int(stored.get("seq", 0))
        except (TypeError, ValueError):
            saved = 0
        self._seq = min(saved + SEQ_SAFETY_MARGIN, 0xFFFFFE)

        self._register_proxy_callback()
        self._background_task = self.hass.async_create_background_task(
            self._connection_loop(),
            f"HeyLight connection {self.network.identifier}",
        )
        self._wake.set()

    async def async_stop(self) -> None:
        self._stopping = True
        if self._unregister_bluetooth is not None:
            self._unregister_bluetooth()
            self._unregister_bluetooth = None

        if self._background_task is not None:
            self._background_task.cancel()
            await asyncio.gather(
                self._background_task, return_exceptions=True
            )
            self._background_task = None

        await self._disconnect()
        await self._save_seq()

    async def async_replace_network(
        self, network: HeylightNetwork
    ) -> None:
        """Replace persisted mesh data and refresh Bluetooth matching."""
        if network.identifier != self.network.identifier:
            raise ValueError(
                "cannot replace a coordinator with a different mesh network"
            )
        self.network = network
        self._register_proxy_callback()
        self._wake.set()

    async def async_begin_provisioning(self) -> None:
        """Release the proxy connection while PB-GATT uses Bluetooth."""
        self._provisioning = True
        self._wake.set()

        async with self._command_lock:
            await self._disconnect()

    async def async_end_provisioning(self) -> None:
        """Allow normal Mesh Proxy connections again."""
        self._provisioning = False
        self._wake.set()

    async def async_force_reconnect(self) -> None:
        """Drop a stale connection and wake the automatic retry loop."""
        if self._stopping:
            raise RuntimeError("HeyLight is shutting down")
        if self._provisioning:
            raise RuntimeError("Cannot reconnect during mesh provisioning")

        # Do not interrupt a command or race an in-progress BLE connection.
        async with self._command_lock:
            async with self._connect_lock:
                if self._stopping or self._provisioning:
                    raise RuntimeError("HeyLight connection is not ready to restart")
                await self._disconnect()
                self.manual_reconnect_requests += 1
                self.last_disconnect_reason = "manual reconnect requested"
                self.last_connection_error = None

        _LOGGER.info("Manual HeyLight Mesh Proxy reconnect requested")
        self._wake.set()

    async def async_wait_connected(
        self, *, timeout: float = 40.0
    ) -> HeylightMeshController:
        """Wait for a matching Mesh Proxy after provisioning."""
        deadline = asyncio.get_running_loop().time() + timeout
        last_error: Exception | None = None

        while asyncio.get_running_loop().time() < deadline:
            try:
                return await self._ensure_connected()
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(1.0)

        if last_error is not None:
            raise TimeoutError(
                f"HeyLight Mesh Proxy did not appear: {last_error}"
            ) from last_error
        raise TimeoutError("HeyLight Mesh Proxy did not appear")

    def async_add_listener(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def async_add_rssi_listener(
        self, listener: Callable[[], None]
    ) -> Callable[[], None]:
        self._rssi_listeners.append(listener)

        def remove() -> None:
            if listener in self._rssi_listeners:
                self._rssi_listeners.remove(listener)

        return remove

    @callback
    def _notify_rssi(self) -> None:
        for listener in tuple(self._rssi_listeners):
            listener()

    @property
    def rssi_age_seconds(self) -> int | None:
        if self._rssi_seen_monotonic is None:
            return None
        return max(0, int(monotonic() - self._rssi_seen_monotonic))

    @property
    def rssi_last_seen_at(self) -> str | None:
        return self._rssi_seen_at.isoformat() if self._rssi_seen_at else None

    @property
    def rssi_dbm(self) -> int | None:
        """Unknown when the last BLE advertisement is over two minutes old."""
        age = self.rssi_age_seconds
        if age is None or age > RSSI_STALE_SECONDS:
            return None
        return self.last_rssi_dbm

    @callback
    def _record_proxy_rssi(self, info: BluetoothServiceInfoBleak) -> None:
        level = getattr(info, "rssi", None)
        if level is None:
            return
        value = int(level)
        if value == 0:
            return
        now = monotonic()
        seen = float(getattr(info, "time", now))
        age = max(0.0, now - seen)
        if age > RSSI_STALE_SECONDS:
            return
        if self._rssi_seen_monotonic is not None and seen < self._rssi_seen_monotonic:
            return
        old = (self.last_rssi_dbm, self.rssi_address, self.rssi_source)
        old_fresh = self._rssi_fresh
        last_published = self._rssi_last_published
        self.last_rssi_dbm = value
        self.rssi_address = info.address
        self.rssi_source = getattr(info, "source", None)
        self._rssi_seen_monotonic = seen
        self._rssi_seen_at = datetime.now(timezone.utc) - timedelta(seconds=age)
        self._rssi_fresh = True
        if (
            not old_fresh
            or old != (self.last_rssi_dbm, self.rssi_address, self.rssi_source)
            or last_published is None
            or now - last_published >= RSSI_REPORT_INTERVAL_SECONDS
        ):
            self._rssi_last_published = now
            self._notify_rssi()

    @callback
    def _refresh_rssi(self) -> None:
        """Poll the HA cache because RSSI changes need not trigger callbacks."""
        if self.rssi_address is not None:
            info = bluetooth.async_last_service_info(
                self.hass, self.rssi_address, connectable=True
            )
            if info is None:
                info = bluetooth.async_last_service_info(
                    self.hass, self.rssi_address, connectable=False
                )
            if info is not None:
                self._record_proxy_rssi(info)
        fresh = self.rssi_dbm is not None
        if fresh != self._rssi_fresh:
            self._rssi_fresh = fresh
            self._notify_rssi()

    @callback
    def _proxy_seen(self, info: BluetoothServiceInfoBleak) -> None:
        self._record_proxy_rssi(info)
        self._wake.set()

    async def _connection_loop(self) -> None:
        while True:
            self._refresh_rssi()
            if self._controller is not None:
                client_connected = bool(
                    self._client is not None
                    and getattr(self._client, "is_connected", False)
                )
                bearer_failed = bool(
                    getattr(
                        getattr(self._controller, "_bearer", None),
                        "failure",
                        None,
                    )
                )
                if (
                    self._provisioning
                    or not client_connected
                    or bearer_failed
                ):
                    self.last_disconnect_reason = (
                        "provisioning requested"
                        if self._provisioning
                        else (
                            "link check failed"
                            if not client_connected
                            else "notification subscription failed"
                        )
                    )
                    await self._disconnect()

            if self._controller is None and not self._provisioning:
                self.reconnect_attempts += 1
                try:
                    await self._ensure_connected()
                except Exception as exc:
                    self.last_connection_error = str(exc)
                    _LOGGER.debug(
                        "HeyLight reconnect attempt failed: %s",
                        exc,
                        exc_info=True,
                    )

            self._wake.clear()
            try:
                await asyncio.wait_for(
                    self._wake.wait(), timeout=RECONNECT_SECONDS
                )
            except TimeoutError:
                pass

    async def _ensure_connected(self) -> HeylightMeshController:
        if self._provisioning:
            raise ConnectionError(
                "Mesh Proxy connection is paused for provisioning"
            )
        if self._controller is not None:
            return self._controller

        async with self._connect_lock:
            if self._provisioning:
                raise ConnectionError(
                    "Mesh Proxy connection is paused for provisioning"
                )
            if self._controller is not None:
                return self._controller

            address = find_proxy_address(
                self.hass,
                self.network.network_id,
                self.network.net_key,
                tuple(node.unicast for node in self.network.nodes),
                self.network.proxy_macs,
            )
            if address is None:
                raise ConnectionError(
                    "no matching HeyLight Mesh Proxy advertisement"
                )
            recent = bluetooth.async_last_service_info(
                self.hass, address, connectable=True
            )
            if recent is not None:
                self._record_proxy_rssi(recent)

            client, bearer = await async_connect_bearer(
                self.hass, address
            )
            if self._provisioning:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                raise ConnectionError(
                    "Mesh Proxy connection was paused during connection"
                )

            controller = HeylightMeshController(
                bearer,
                net_key=self.network.net_key,
                app_key=self.network.app_key,
                iv_index=self.network.iv_index,
                src_addr=DEFAULT_SOURCE_ADDRESS,
                seq=self._seq,
            )
            try:
                await controller.start()
            except Exception:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                raise

            self._client = client
            self._controller = controller
            self.connected_address = address
            self._seq = controller.seq
            self.available = True
            self.successful_connections += 1
            self.last_connection_error = None
            self.last_disconnect_reason = None
            self._notify()
            await self._save_seq()

            set_callback = getattr(
                client, "set_disconnected_callback", None
            )
            if callable(set_callback):
                set_callback(
                    lambda _client: self.hass.loop.call_soon_threadsafe(
                        self._schedule_drop, client
                    )
                )

            _LOGGER.info(
                "Connected to HeyLight Mesh Proxy %s", address
            )
            return controller

    @callback
    def _schedule_drop(self, client: Any) -> None:
        # Ignore delayed disconnect callbacks from a superseded BLE client.
        if self._stopping or client is not self._client:
            return
        self.last_disconnect_reason = "Bleak disconnected callback"
        self.hass.async_create_background_task(
            self._disconnect(),
            f"HeyLight disconnect {self.network.identifier}",
        )
        self._wake.set()

    async def _disconnect(self) -> None:
        async with self._disconnect_lock:
            controller, self._controller = self._controller, None
            client, self._client = self._client, None
            self.connected_address = None

            if controller is not None:
                self._seq = controller.seq
                try:
                    await controller.stop()
                except Exception:
                    _LOGGER.debug("controller stop failed", exc_info=True)

            if client is not None:
                try:
                    if getattr(client, "is_connected", False):
                        await client.disconnect()
                except Exception:
                    _LOGGER.debug(
                        "Bluetooth disconnect failed", exc_info=True
                    )

            if self.available:
                self.available = False
                self._notify()

    async def _save_seq(self) -> None:
        await self._store.async_save({"seq": self._seq})

    async def _run_connected(
        self, call: Callable[[HeylightMeshController], Any]
    ) -> Any:
        """Serialize a command, connect when needed, and persist sequence."""
        async with self._command_lock:
            controller = await self._ensure_connected()
            try:
                result = call(controller)
                if hasattr(result, "__await__"):
                    result = await result
                await controller.flush()
                self._seq = controller.seq
                await self._save_seq()
                return result
            except Exception:
                self._seq = controller.seq
                await self._save_seq()
                await self._disconnect()
                self._wake.set()
                raise
