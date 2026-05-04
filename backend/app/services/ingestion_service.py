from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
from pathlib import Path

import aiofiles

from app.core.config import settings
from app.core.errors import ValidationAppError


def _sanitize_filename(filename: str) -> str:
    cleaned = os.path.basename(filename).strip()
    if not cleaned:
        raise ValidationAppError("Filename is required")
    return cleaned


def _guess_mime_type(filename: str, declared: str | None) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    mime = (declared or "").strip() or (guessed or "").strip()
    if not mime:
        raise ValidationAppError("Could not determine MIME type")
    return mime


def _infer_doc_type(filename: str, mime_type: str) -> str:
    lower = filename.lower()
    if lower.endswith(".md") or mime_type == "text/markdown":
        return "markdown"
    if lower.endswith(".txt") or mime_type == "text/plain":
        return "text"
    if lower.endswith(".pdf") or mime_type == "application/pdf":
        return "pdf"
    if lower.endswith(".docx") or mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return "docx"
    return "unknown"


def _validate_extension_for_mime(filename: str, mime_type: str) -> None:
    lower = filename.lower()
    allowed_extensions = {
        "text/plain": (".txt",),
        "text/markdown": (".md", ".markdown"),
        "application/pdf": (".pdf",),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",),
    }
    expected = allowed_extensions.get(mime_type)
    if not expected:
        raise ValidationAppError("MIME type is not allowed")
    if not lower.endswith(expected):
        raise ValidationAppError("File extension does not match MIME type")


async def save_upload_to_temp(
    *,
    filename: str,
    declared_content_type: str | None,
    file_bytes: bytes,
) -> tuple[str, str, str, str, int, str, str]:
    if len(file_bytes) > settings.max_upload_bytes:
        raise ValidationAppError("File is too large")

    safe_name = _sanitize_filename(filename)
    mime_type = _guess_mime_type(safe_name, declared_content_type)
    if mime_type not in settings.allowed_mime_types:
        raise ValidationAppError("MIME type is not allowed")
    _validate_extension_for_mime(safe_name, mime_type)

    doc_type = _infer_doc_type(safe_name, mime_type)
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    doc_id = uuid.uuid4().hex
    temp_dir = Path(settings.upload_temp_dir) / doc_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_name

    async with aiofiles.open(temp_path, "wb") as handle:
        await handle.write(file_bytes)

    return doc_id, str(temp_path), safe_name, mime_type, len(file_bytes), sha256, doc_type
