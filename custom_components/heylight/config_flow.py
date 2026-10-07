"""Configuration and commissioning flows for HeyLight."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    FileSelector,
    FileSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .btmesh.configuration import async_configure_node
from .const import CONF_SHARE_JSON, DOMAIN
from .provisioner import (
    UnprovisionedDevice,
    async_provision_device,
    async_scan_unprovisioned,
    next_unicast_address,
    validate_unicast_address,
)
from .share import (
    ShareDataError,
    append_provisioned_node,
    create_managed_share_text,
    finalize_provisioned_node,
    normalize_share_text,
    parse_share_text,
)

_LOGGER = logging.getLogger(__name__)

CONF_QR_TEXT = "qr_text"
CONF_QR_IMAGE = "qr_image"
CONF_NETWORK_NAME = "network_name"
CONF_DEVICE = "device"
CONF_DEVICE_NAME = "device_name"
CONF_UNICAST_ADDRESS = "unicast_address"

STEP_IMPORT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_QR_TEXT): TextSelector(
            TextSelectorConfig(
                multiline=True, type=TextSelectorType.TEXT
            )
        ),
        vol.Optional(CONF_QR_IMAGE): FileSelector(
            FileSelectorConfig(
                accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
            )
        ),
    }
)


def _decode_qr_image(path: Path) -> str:
    """Decode the first QR code from an uploaded image."""
    from PIL import Image
    from pyzbar import pyzbar

    with Image.open(path) as image:
        barcodes = pyzbar.decode(image)

    for barcode in barcodes:
        data = getattr(barcode, "data", b"")
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="strict").strip()
        else:
            text = str(data).strip()
        if text:
            return text

    raise ShareDataError("no QR code was found in the uploaded image")


def _decode_uploaded_qr(
    hass: HomeAssistant, uploaded_file_id: str
) -> str:
    """Open and decode an uploaded image entirely in the executor thread."""
    with process_uploaded_file(hass, uploaded_file_id) as uploaded:
        return _decode_qr_image(uploaded)


class HeylightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up an imported or integration-managed HeyLight mesh."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="user",
            menu_options=["import_share", "create_network"],
        )

    async def async_step_import_share(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Import a HeyLight Share Device QR payload."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if user_input is not None:
            qr_text = str(user_input.get(CONF_QR_TEXT) or "").strip()
            upload_id = user_input.get(CONF_QR_IMAGE)

            if not qr_text and not upload_id:
                errors["base"] = "missing_input"
            elif qr_text and upload_id:
                errors["base"] = "choose_one"
            else:
                try:
                    if upload_id:
                        qr_text = await self.hass.async_add_executor_job(
                            _decode_uploaded_qr,
                            self.hass,
                            str(upload_id),
                        )

                    network = parse_share_text(qr_text)
                    normalized = normalize_share_text(qr_text)
                except ShareDataError as exc:
                    _LOGGER.debug(
                        "HeyLight QR import failed: %s", exc
                    )
                    errors["base"] = "invalid_share"
                    description_placeholders["reason"] = str(exc)
                except Exception as exc:
                    _LOGGER.debug(
                        "HeyLight QR image decoding failed",
                        exc_info=True,
                    )
                    errors["base"] = "invalid_qr"
                    description_placeholders["reason"] = str(exc)
                else:
                    await self.async_set_unique_id(network.identifier)
                    self._abort_if_unique_id_configured()
                    title = (
                        network.nodes[0].name
                        if len(network.nodes) == 1
                        else f"HeyLight {network.mesh_name}"
                    )
                    return self.async_create_entry(
                        title=title,
                        data={CONF_SHARE_JSON: normalized},
                    )

        return self.async_show_form(
            step_id="import_share",
            data_schema=STEP_IMPORT_SCHEMA,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_create_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a new integration-owned Bluetooth Mesh network."""
        if user_input is not None:
            text = create_managed_share_text(
                str(user_input[CONF_NETWORK_NAME])
            )
            network = parse_share_text(text)
            await self.async_set_unique_id(network.identifier)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=network.title,
                data={CONF_SHARE_JSON: text},
            )

        return self.async_show_form(
            step_id="create_network",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NETWORK_NAME,
                        default="HeyLight Mesh",
                    ): str,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        return HeylightOptionsFlow()


class HeylightOptionsFlow(OptionsFlow):
    """Provision and finish commissioning HeyLight nodes."""

    def __init__(self) -> None:
        self._scan_task: asyncio.Task | None = None
        self._devices: list[UnprovisionedDevice] = []
        self._selected_device: UnprovisionedDevice | None = None
        self._device_name = "HeyLight"
        self._requested_unicast: int | None = None
        self._commission_task: asyncio.Task | None = None
        self._commission_error: str | None = None
        self._commission_pending = False
        self._pending_unicast: int | None = None

    @property
    def _network(self):
        return parse_share_text(
            self.config_entry.data[CONF_SHARE_JSON]
        )

    @property
    def _coordinator(self):
        return self.config_entry.runtime_data

    def _pending_nodes(self):
        return [
            node for node in self._network.nodes if not node.configured
        ]

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = ["add_device"]
        if self._pending_nodes():
            options.append("finish_setup")
        return self.async_show_menu(
            step_id="init",
            menu_options=options,
        )

    async def async_step_add_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Actively scan for devices exposing the Mesh Provisioning service."""
        if self._scan_task is None:
            self._devices = []
            self._scan_task = self.hass.async_create_task(
                async_scan_unprovisioned(self.hass)
            )

        if self._scan_task.done():
            try:
                self._devices = self._scan_task.result()
            except Exception as exc:
                _LOGGER.debug(
                    "HeyLight unprovisioned scan failed",
                    exc_info=True,
                )
                self._commission_error = str(exc)
                self._devices = []
            finally:
                self._scan_task = None

            return self.async_show_progress_done(
                next_step_id="select_device"
            )

        return self.async_show_progress(
            step_id="add_device",
            progress_action="scan_unprovisioned",
            progress_task=self._scan_task,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose one discovered unprovisioned device."""
        if not self._devices:
            if user_input is not None:
                self._scan_task = None
                return await self.async_step_add_device()

            return self.async_show_form(
                step_id="select_device",
                data_schema=vol.Schema({}),
                errors={"base": "no_unprovisioned_devices"},
            )

        choices = {}
        for device in self._devices:
            suffix = (
                f", RSSI {device.rssi} dBm"
                if device.rssi is not None
                else ""
            )
            choices[device.address] = (
                f"{device.name} ({device.address}{suffix})"
            )

        if user_input is not None:
            address = str(user_input[CONF_DEVICE])
            self._selected_device = next(
                device
                for device in self._devices
                if device.address == address
            )
            self._device_name = self._selected_device.name
            return await self.async_step_device_details()

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE): vol.In(choices)}
            ),
        )

    async def async_step_device_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Name the node and optionally choose its unicast address."""
        network = self._network
        errors: dict[str, str] = {}

        if user_input is not None:
            self._device_name = (
                str(user_input[CONF_DEVICE_NAME]).strip()
                or "HeyLight"
            )
            self._requested_unicast = None

            if not network.managed:
                raw_address = str(
                    user_input[CONF_UNICAST_ADDRESS]
                ).strip()
                try:
                    address = int(raw_address, 0)
                    validate_unicast_address(network, address, 1)
                except (ValueError, TypeError):
                    errors[CONF_UNICAST_ADDRESS] = (
                        "invalid_unicast_address"
                    )
                else:
                    self._requested_unicast = address

            if not errors:
                self._commission_task = None
                self._commission_error = None
                self._commission_pending = False
                return await self.async_step_provision()

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_DEVICE_NAME,
                default=self._device_name or "HeyLight",
            ): str
        }
        if not network.managed:
            try:
                suggested = next_unicast_address(network, 1)
            except ValueError:
                suggested = 1
            schema[
                vol.Required(
                    CONF_UNICAST_ADDRESS,
                    default=f"0x{suggested:04X}",
                )
            ] = str

        return self.async_show_form(
            step_id="device_details",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    async def _async_commission_selected(self) -> None:
        """Provision, persist, configure and finalize the selected node."""
        device = self._selected_device
        if device is None:
            self._commission_error = "no device was selected"
            return

        coordinator = self._coordinator
        network = self._network
        provisioning_started = False

        try:
            await coordinator.async_begin_provisioning()
            provisioning_started = True

            if network.managed:
                allocate = lambda count: next_unicast_address(
                    network, count
                )
            else:
                requested = self._requested_unicast
                if requested is None:
                    raise ValueError(
                        "an imported network requires a unicast address"
                    )
                allocate = lambda count: validate_unicast_address(
                    network, requested, count
                )

            result = await async_provision_device(
                self.hass,
                address=device.address,
                net_key=network.net_key,
                iv_index=network.iv_index,
                allocate_unicast=allocate,
            )

            pending_text = append_provisioned_node(
                self.config_entry.data[CONF_SHARE_JSON],
                name=self._device_name,
                mac=device.address,
                unicast=result.unicast,
                device_key=result.device_key,
                element_count=result.element_count,
            )
            new_data = dict(self.config_entry.data)
            new_data[CONF_SHARE_JSON] = pending_text
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )

            pending_network = parse_share_text(pending_text)
            await coordinator.async_replace_network(pending_network)
            self._commission_pending = True
            self._pending_unicast = result.unicast

        except Exception as exc:
            self._commission_error = str(exc)
            _LOGGER.exception("HeyLight provisioning failed")
            return
        finally:
            if provisioning_started:
                await coordinator.async_end_provisioning()

        await self._async_finish_pending(self._pending_unicast)

    async def _async_finish_pending(
        self, unicast: int | None
    ) -> None:
        """Run Config Server commissioning for an already provisioned node."""
        if unicast is None:
            self._commission_error = "missing provisioned node address"
            return

        coordinator = self._coordinator
        network = self._network
        node = next(
            (
                item
                for item in network.nodes
                if item.unicast == unicast and not item.configured
            ),
            None,
        )
        if node is None:
            self._commission_error = (
                f"pending node 0x{unicast:04X} was not found"
            )
            return

        try:
            await coordinator.async_wait_connected(timeout=45.0)
            composition = await coordinator._run_connected(
                lambda controller: async_configure_node(
                    controller,
                    unicast=node.unicast,
                    device_key=node.device_key,
                    app_key=network.app_key,
                )
            )

            final_text = finalize_provisioned_node(
                self.config_entry.data[CONF_SHARE_JSON],
                unicast=node.unicast,
                composition=composition,
            )
            new_data = dict(self.config_entry.data)
            new_data[CONF_SHARE_JSON] = final_text
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=new_data,
            )
            await coordinator.async_replace_network(
                parse_share_text(final_text)
            )
            self._commission_pending = False
            self._commission_error = None
        except Exception as exc:
            self._commission_pending = True
            self._commission_error = str(exc)
            _LOGGER.exception(
                "HeyLight post-provision commissioning failed"
            )

    async def async_step_provision(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show progress while the selected node is commissioned."""
        if self._commission_task is None:
            self._commission_task = self.hass.async_create_task(
                self._async_commission_selected()
            )

        if self._commission_task.done():
            self._commission_task.result()
            self._commission_task = None
            return self.async_show_progress_done(
                next_step_id=(
                    "provision_failed"
                    if self._commission_error
                    else "provision_complete"
                )
            )

        return self.async_show_progress(
            step_id="provision",
            progress_action="provision_device",
            progress_task=self._commission_task,
        )

    async def async_step_finish_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a previously provisioned node whose setup was interrupted."""
        pending = self._pending_nodes()
        if not pending:
            return await self.async_step_init()

        choices = {
            str(node.unicast): (
                f"{node.name} — 0x{node.unicast:04X} ({node.mac})"
            )
            for node in pending
        }

        if user_input is not None:
            self._pending_unicast = int(
                str(user_input[CONF_DEVICE]), 0
            )
            self._commission_error = None
            self._commission_pending = True
            self._commission_task = None
            return await self.async_step_finish_progress()

        return self.async_show_form(
            step_id="finish_setup",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE): vol.In(choices)}
            ),
        )

    async def async_step_finish_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show progress while Config Server setup is retried."""
        if self._commission_task is None:
            self._commission_task = self.hass.async_create_task(
                self._async_finish_pending(self._pending_unicast)
            )

        if self._commission_task.done():
            self._commission_task.result()
            self._commission_task = None
            return self.async_show_progress_done(
                next_step_id=(
                    "provision_failed"
                    if self._commission_error
                    else "provision_complete"
                )
            )

        return self.async_show_progress(
            step_id="finish_progress",
            progress_action="finish_commissioning",
            progress_task=self._commission_task,
        )

    async def async_step_provision_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain a provisioning/configuration failure."""
        if user_input is not None:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="provision_failed",
            data_schema=vol.Schema({}),
            description_placeholders={
                "reason": self._commission_error or "unknown error",
            },
        )

    async def async_step_provision_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Close the flow and reload platforms so new entities appear."""
        self.hass.async_create_task(
            self.hass.config_entries.async_reload(
                self.config_entry.entry_id
            )
        )
        return self.async_create_entry(title="", data={})
