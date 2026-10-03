"""Configuration flow for HeyLight Share Device QR data."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    FileSelector,
    FileSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import CONF_SHARE_JSON, DOMAIN
from .share import (
    ShareDataError,
    normalize_share_text,
    parse_share_text,
)

_LOGGER = logging.getLogger(__name__)

CONF_QR_TEXT = "qr_text"
CONF_QR_IMAGE = "qr_image"

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_QR_TEXT): TextSelector(
            TextSelectorConfig(
                multiline=True, type=TextSelectorType.TEXT
            )
        ),
        vol.Optional(CONF_QR_IMAGE): FileSelector(
            FileSelectorConfig(
                accept=(
                    ".png,.jpg,.jpeg,.webp,"
                    "image/png,image/jpeg,image/webp"
                )
            )
        ),
    }
)


def _decode_qr_image(path) -> str:
    """Decode the first QR/barcode from an uploaded image."""
    import zxingcpp
    from PIL import Image

    with Image.open(path) as image:
        barcodes = zxingcpp.read_barcodes(image)
    for barcode in barcodes:
        text = getattr(barcode, "text", "")
        if text:
            return text
    raise ShareDataError("no QR code was found in the uploaded image")


class HeylightConfigFlow(ConfigFlow, domain=DOMAIN):
    """Import a Heylight Share Device QR payload."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
                        with process_uploaded_file(
                            self.hass, upload_id
                        ) as uploaded:
                            qr_text = await self.hass.async_add_executor_job(
                                _decode_qr_image, uploaded
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
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders=description_placeholders,
        )
