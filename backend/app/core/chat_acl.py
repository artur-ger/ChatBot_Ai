from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings
from app.core.errors import ValidationAppError


def make_chat_signature(chat_id: str, secret: str | None = None) -> str:
    key = (secret or settings.chat_acl_secret).encode("utf-8")
    return hmac.new(key, chat_id.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_chat_access(*, chat_id: str, provided_signature: str | None) -> None:
    expected = make_chat_signature(chat_id)
    if not provided_signature or not hmac.compare_digest(provided_signature, expected):
        raise ValidationAppError("Access denied for provided chat_id")
