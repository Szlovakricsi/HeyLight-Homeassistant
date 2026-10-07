"""Bluetooth Mesh PB-GATT provisioning primitives for HeyLight.

This module implements the Bluetooth Mesh 1.0 provisioning path used by the
tested HeyLight/Telink devices: P-256 ECDH, AES-CMAC confirmation and No-OOB
authentication.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import hmac
import os

from cryptography.hazmat.primitives.asymmetric import ec

from .crypto import aes_cmac, ccm_encrypt, k1, s1

PDU_INVITE = 0x00
PDU_CAPABILITIES = 0x01
PDU_START = 0x02
PDU_PUBLIC_KEY = 0x03
PDU_CONFIRMATION = 0x05
PDU_RANDOM = 0x06
PDU_DATA = 0x07
PDU_COMPLETE = 0x08
PDU_FAILED = 0x09

ALGORITHM_FIPS_P256_CMAC_AES128_AES_CCM = 0x0001


class ProvisioningError(Exception):
    """Bluetooth Mesh provisioning failed."""


@dataclass(frozen=True, slots=True)
class ProvisioningCapabilities:
    """Capabilities reported by an unprovisioned node."""

    num_elements: int
    algorithms: int
    public_key_type: int
    static_oob_type: int
    output_oob_size: int
    output_oob_actions: int
    input_oob_size: int
    input_oob_actions: int
    raw: bytes


@dataclass(frozen=True, slots=True)
class ProvisioningResult:
    """Result of one successful provisioning transaction."""

    device_key: bytes
    unicast: int
    element_count: int


def _parse_capabilities(payload: bytes) -> ProvisioningCapabilities:
    if len(payload) != 11:
        raise ProvisioningError(
            f"invalid Capabilities length {len(payload)} (expected 11)"
        )
    return ProvisioningCapabilities(
        num_elements=payload[0],
        algorithms=int.from_bytes(payload[1:3], "big"),
        public_key_type=payload[3],
        static_oob_type=payload[4],
        output_oob_size=payload[5],
        output_oob_actions=int.from_bytes(payload[6:8], "big"),
        input_oob_size=payload[8],
        input_oob_actions=int.from_bytes(payload[9:11], "big"),
        raw=bytes(payload),
    )


def _public_key_bytes(private_key: ec.EllipticCurvePrivateKey) -> bytes:
    numbers = private_key.public_key().public_numbers()
    return numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")


def _ecdh_secret(
    private_key: ec.EllipticCurvePrivateKey, peer: bytes
) -> bytes:
    if len(peer) != 64:
        raise ProvisioningError("device public key is not 64 bytes")

    x = int.from_bytes(peer[:32], "big")
    y = int.from_bytes(peer[32:], "big")
    try:
        public_key = ec.EllipticCurvePublicNumbers(
            x, y, ec.SECP256R1()
        ).public_key()
    except ValueError as exc:
        raise ProvisioningError("device supplied an invalid P-256 key") from exc

    return private_key.exchange(ec.ECDH(), public_key)


class MeshProvisioner:
    """Run a single PB-GATT provisioning exchange."""

    def __init__(
        self,
        bearer,
        *,
        net_key: bytes,
        iv_index: int,
        allocate_unicast: Callable[[int], int],
        on_data_ready: (
            Callable[[ProvisioningResult], Awaitable[None] | None] | None
        ) = None,
    ) -> None:
        if len(net_key) != 16:
            raise ValueError("net_key must be 16 bytes")
        if not 0 <= int(iv_index) <= 0xFFFFFFFF:
            raise ValueError("iv_index must fit in 32 bits")

        self._bearer = bearer
        self._net_key = bytes(net_key)
        self._iv_index = int(iv_index)
        self._allocate_unicast = allocate_unicast
        self._on_data_ready = on_data_ready

    async def _send(self, pdu_type: int, payload: bytes = b"") -> None:
        await self._bearer.send(bytes([pdu_type]) + payload)

    async def _receive(
        self, expected_type: int, *, timeout: float = 15.0
    ) -> bytes:
        raw = await self._bearer.receive(timeout=timeout)
        if not raw:
            raise ProvisioningError("received an empty provisioning PDU")

        pdu_type, payload = raw[0], raw[1:]
        if pdu_type == PDU_FAILED:
            code = payload[0] if payload else 0xFF
            raise ProvisioningError(
                f"device rejected provisioning (error 0x{code:02X})"
            )
        if pdu_type != expected_type:
            raise ProvisioningError(
                f"unexpected provisioning PDU 0x{pdu_type:02X}; "
                f"expected 0x{expected_type:02X}"
            )
        return payload

    async def run(self) -> ProvisioningResult:
        """Provision the connected device into the supplied mesh network."""
        private_key = ec.generate_private_key(ec.SECP256R1())
        provisioner_public = _public_key_bytes(private_key)

        invite = b"\x00"
        await self._send(PDU_INVITE, invite)
        capabilities_raw = await self._receive(PDU_CAPABILITIES)
        capabilities = _parse_capabilities(capabilities_raw)

        if capabilities.num_elements < 1:
            raise ProvisioningError("device reports zero elements")
        if not (
            capabilities.algorithms
            & ALGORITHM_FIPS_P256_CMAC_AES128_AES_CCM
        ):
            raise ProvisioningError(
                "device does not support the AES-CMAC P-256 provisioning "
                "algorithm used by the tested HeyLight devices"
            )

        # Algorithm 0, in-band public key, No-OOB authentication.
        start = b"\x00\x00\x00\x00\x00"
        await self._send(PDU_START, start)
        await self._send(PDU_PUBLIC_KEY, provisioner_public)

        device_public = await self._receive(PDU_PUBLIC_KEY)
        if len(device_public) != 64:
            raise ProvisioningError("invalid device public-key length")

        secret = _ecdh_secret(private_key, device_public)
        confirmation_inputs = (
            invite
            + capabilities.raw
            + start
            + provisioner_public
            + device_public
        )
        if len(confirmation_inputs) != 145:
            raise ProvisioningError("invalid confirmation input length")

        confirmation_salt = s1(confirmation_inputs)
        confirmation_key = k1(secret, confirmation_salt, b"prck")
        auth_value = bytes(16)

        provisioner_random = os.urandom(16)
        provisioner_confirmation = aes_cmac(
            confirmation_key, provisioner_random + auth_value
        )
        await self._send(PDU_CONFIRMATION, provisioner_confirmation)

        device_confirmation = await self._receive(PDU_CONFIRMATION)
        if len(device_confirmation) != 16:
            raise ProvisioningError("invalid device confirmation length")

        await self._send(PDU_RANDOM, provisioner_random)
        device_random = await self._receive(PDU_RANDOM)
        if len(device_random) != 16:
            raise ProvisioningError("invalid device random length")

        expected_confirmation = aes_cmac(
            confirmation_key, device_random + auth_value
        )
        if not hmac.compare_digest(
            device_confirmation, expected_confirmation
        ):
            raise ProvisioningError("device confirmation authentication failed")

        provisioning_salt = s1(
            confirmation_salt + provisioner_random + device_random
        )
        session_key = k1(secret, provisioning_salt, b"prsk")
        session_nonce = k1(secret, provisioning_salt, b"prsn")[3:]
        device_key = k1(secret, provisioning_salt, b"prdk")

        unicast = int(self._allocate_unicast(capabilities.num_elements))
        if not 1 <= unicast <= 0x7FFF:
            raise ProvisioningError("allocated unicast address is invalid")
        if unicast + capabilities.num_elements - 1 > 0x7FFF:
            raise ProvisioningError(
                "allocated unicast range exceeds the unicast address space"
            )

        plaintext = (
            self._net_key
            + (0).to_bytes(2, "big")
            + b"\x00"
            + self._iv_index.to_bytes(4, "big")
            + unicast.to_bytes(2, "big")
        )
        encrypted = ccm_encrypt(
            session_key, session_nonce, plaintext, 8
        )
        if len(encrypted) != 33:
            raise ProvisioningError("invalid encrypted provisioning-data size")

        result = ProvisioningResult(
            device_key=device_key,
            unicast=unicast,
            element_count=capabilities.num_elements,
        )

        # Persist the DeviceKey/address before crossing the irreversible
        # Provisioning Data boundary. If the UI is closed or the Complete PDU
        # is lost after this point, Home Assistant can still resume Config
        # Server setup instead of losing the node credentials.
        if self._on_data_ready is not None:
            callback_result = self._on_data_ready(result)
            if callback_result is not None:
                await callback_result

        await self._send(PDU_DATA, encrypted)
        complete = await self._receive(PDU_COMPLETE, timeout=20.0)
        if complete:
            raise ProvisioningError("Provisioning Complete contained payload")

        return result
