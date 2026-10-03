"""Bluetooth Mesh security primitives.

Derived from dasimon135/ha-bluetooth-mesh (MIT), copyright David Simon.
"""

from typing import NamedTuple

from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.cmac import CMAC

ZERO_KEY = bytes(16)


class K2Output(NamedTuple):
    nid: int
    encryption_key: bytes
    privacy_key: bytes


def aes_cmac(key: bytes, data: bytes) -> bytes:
    c = CMAC(AES(key))
    c.update(data)
    return c.finalize()


def aes_ecb(key: bytes, block: bytes) -> bytes:
    encryptor = Cipher(AES(key), modes.ECB()).encryptor()
    return encryptor.update(block) + encryptor.finalize()


def s1(m: bytes) -> bytes:
    return aes_cmac(ZERO_KEY, m)


def k1(n: bytes, salt: bytes, p: bytes) -> bytes:
    return aes_cmac(aes_cmac(salt, n), p)


def k2(n: bytes, p: bytes) -> K2Output:
    salt = s1(b"smk2")
    t = aes_cmac(salt, n)
    t1 = aes_cmac(t, p + b"\x01")
    t2 = aes_cmac(t, t1 + p + b"\x02")
    t3 = aes_cmac(t, t2 + p + b"\x03")
    return K2Output(t1[15] & 0x7F, t2, t3)


def k3(n: bytes) -> bytes:
    salt = s1(b"smk3")
    t = aes_cmac(salt, n)
    return aes_cmac(t, b"id64\x01")[8:]


def k4(n: bytes) -> int:
    salt = s1(b"smk4")
    t = aes_cmac(salt, n)
    return aes_cmac(t, b"id6\x01")[15] & 0x3F


def ccm_encrypt(
    key: bytes, nonce: bytes, plaintext: bytes, mic_len: int, aad: bytes = b""
) -> bytes:
    return AESCCM(key, tag_length=mic_len).encrypt(nonce, plaintext, aad)


def ccm_decrypt(
    key: bytes, nonce: bytes, data: bytes, mic_len: int, aad: bytes = b""
) -> bytes:
    return AESCCM(key, tag_length=mic_len).decrypt(nonce, data, aad)
