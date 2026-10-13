"""Encryption at rest for manuscript content (docs/SPEC_REVIEW.md S3).

AES-256-GCM with a server key from the environment (`NIS_MASTER_KEY`, 32 bytes, base64). Encrypted values carry
the prefix `enc:v1:` so plaintext rows written before the key was configured stay readable and can be migrated
with `nis encrypt-existing`. Threat model, stated honestly: this protects database files, dumps and backups;
it does NOT hide content from someone who controls the running server and its environment.
"""

import base64
import json
import os
from functools import lru_cache
from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

PREFIX = "enc:v1:"


class KeyMissing(RuntimeError):
    pass


@lru_cache
def _aead():
    raw = os.environ.get("NIS_MASTER_KEY", "").strip()
    if not raw:
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError("NIS_MASTER_KEY must be 32 bytes, base64-encoded")
    return AESGCM(key)


def reset() -> None:
    _aead.cache_clear()


def enabled() -> bool:
    return _aead() is not None


def seal(text: str) -> str:
    a = _aead()
    if a is None:
        return text
    nonce = os.urandom(12)
    return PREFIX + base64.b64encode(nonce + a.encrypt(nonce, text.encode(), PREFIX.encode())).decode()


def open_(value: str) -> str:
    if not value.startswith(PREFIX):
        return value  # legacy plaintext
    a = _aead()
    if a is None:
        raise KeyMissing("المحتوى مشفّر ولم يُضبط NIS_MASTER_KEY على هذا الخادم.")
    blob = base64.b64decode(value[len(PREFIX):])
    return a.decrypt(blob[:12], blob[12:], PREFIX.encode()).decode()


def new_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:
        return None if value is None else seal(value)

    def process_result_value(self, value: Any, dialect) -> Any:
        return None if value is None else open_(value)


class EncryptedJSON(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> Any:
        return None if value is None else seal(json.dumps(value, ensure_ascii=False))

    def process_result_value(self, value: Any, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, (dict, list)):  # a JSON column that has not been migrated yet
            return value
        return json.loads(open_(value))
