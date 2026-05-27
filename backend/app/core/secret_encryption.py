from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.errors import ValidationAppError

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    key = settings.llm_settings_encryption_key
    if not key:
        raise ValidationAppError(
            "LLM_SETTINGS_ENCRYPTION_KEY is not configured; cannot store API keys"
        )
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise ValidationAppError("LLM_SETTINGS_ENCRYPTION_KEY is invalid") from exc


def encrypt_secret(value: str) -> str:
    token = _fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValidationAppError("Stored API key could not be decrypted") from exc


def mask_api_key(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def generate_encryption_key() -> str:
    return Fernet.generate_key().decode("utf-8")
