"""Connection lifecycle and command serialization for HeyLight."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .btmesh.controller import HeylightMeshController
from .const import DEFAULT_SOURCE_ADDRESS, IV_INDEX
from .mesh_transport import (
    async_connect_bearer,
    async_register_proxy_callback,
    find_proxy_address,
)
from .share import HeylightNetwork

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
SEQ_SAFETY_MARGIN = 32
RECONNECT_SECONDS = 5


class HeylightCoordinator:
    """One runtime per imported HeyLight mesh network."""

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
        self._connect_lock = asyncio.Lock()
        self._disconnect_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._background_task: asyncio.Task | None = None
        self._unregister_bluetooth: Callable[[], None] | None = None
        self._stopping = False
        self.reconnect_attempts = 0
        self.successful_connections = 0
        self.last_connection_error: str | None = None
        self.last_disconnect_reason: str | None = None

        self._store: Store = Store(
            hass, STORE_VERSION, f"heylight_seq_{entry_id}"
        )
        self._seq = 0

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        try:
            saved = int(stored.get("seq", 0))
        except (TypeError, ValueError):
            saved = 0
        self._seq = min(saved + SEQ_SAFETY_MARGIN, 0xFFFFFE)

        self._unregister_bluetooth = async_register_proxy_callback(
            self.hass,
            self.network.network_id,
            self.network.net_key,
            tuple(node.unicast for node in self.network.nodes),
            self.network.proxy_macs,
            self._proxy_seen,
        )
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

    @callback
    def _proxy_seen(self, _address: str) -> None:
        self._wake.set()

    async def _connection_loop(self) -> None:
        while True:
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
                if not client_connected or bearer_failed:
                    self.last_disconnect_reason = (
                        "link check failed"
                        if not client_connected
                        else "notification subscription failed"
                    )
                    await self._disconnect()

            if self._controller is None:
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
        if self._controller is not None:
            return self._controller

        async with self._connect_lock:
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

            client, bearer = await async_connect_bearer(
                self.hass, address
            )
            controller = HeylightMeshController(
                bearer,
                net_key=self.network.net_key,
                app_key=self.network.app_key,
                iv_index=IV_INDEX,
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
                        self._schedule_drop
                    )
                )

            _LOGGER.info(
                "Connected to HeyLight Mesh Proxy %s", address
            )
            return controller

    @callback
    def _schedule_drop(self) -> None:
        if self._stopping:
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
