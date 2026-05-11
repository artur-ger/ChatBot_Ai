from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

import aiofiles

from app.core.config import settings
from app.core.errors import ValidationAppError

_ALLOWED_EXTENSIONS_BY_MIME: dict[str, tuple[str, ...]] = {
    "text/plain": (".txt",),
    "text/markdown": (".md", ".markdown"),
    "application/pdf": (".pdf",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",),
}
_BINARY_DECLARED_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
_EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
_FORBIDDEN_DOCX_PARTS = (
    "vbaproject.bin",
    "activeX/",
    "embeddings/oleObject",
    "oleObject",
)


def _sanitize_filename(filename: str) -> str:
    cleaned = os.path.basename(filename).strip().replace("\x00", "")
    if not cleaned or cleaned in {".", ".."}:
        raise ValidationAppError("Filename is required")
    return cleaned


def _normalize_mime_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _guess_mime_type(filename: str, declared: str | None) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    declared_mime = _normalize_mime_type(declared)
    guessed_mime = _normalize_mime_type(guessed)

    if declared_mime not in _BINARY_DECLARED_MIME_TYPES:
        return declared_mime
    if guessed_mime:
        return guessed_mime
    raise ValidationAppError("Could not determine MIME type")


def _infer_doc_type(filename: str, mime_type: str) -> str:
    lower = filename.lower()
    if lower.endswith((".md", ".markdown")) or mime_type == "text/markdown":
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
    expected = _ALLOWED_EXTENSIONS_BY_MIME.get(mime_type)
    if not expected:
        raise ValidationAppError("MIME type is not allowed")
    if not lower.endswith(expected):
        raise ValidationAppError("File extension does not match MIME type")


def _validate_magic_header(*, doc_type: str, file_bytes: bytes) -> None:
    if doc_type == "pdf" and not file_bytes.startswith(b"%PDF"):
        raise ValidationAppError("PDF signature is invalid")
    if doc_type == "docx" and not file_bytes.startswith(b"PK"):
        raise ValidationAppError("DOCX signature is invalid")


def _validate_text_payload(file_bytes: bytes) -> None:
    if not file_bytes:
        raise ValidationAppError("File is empty")
    sample = file_bytes[:8192]
    if not sample:
        raise ValidationAppError("File is empty")
    control_count = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13})
    if control_count / max(len(sample), 1) > 0.05:
        raise ValidationAppError("Text file contains too many binary control characters")


def _basic_sanitization_scan(*, doc_type: str, file_bytes: bytes) -> None:
    if _EICAR_MARKER in file_bytes:
        raise ValidationAppError("File failed antivirus scan")

    _validate_magic_header(doc_type=doc_type, file_bytes=file_bytes)

    if doc_type in {"text", "markdown"}:
        _validate_text_payload(file_bytes)
        return

    if doc_type != "docx":
        return

    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
            names = [name.replace("\\", "/") for name in archive.namelist()]
    except zipfile.BadZipFile as exc:
        raise ValidationAppError("DOCX archive is invalid") from exc

    lowered_names = [name.lower() for name in names]
    if "[content_types].xml" not in lowered_names or not any(
        name.startswith("word/") for name in lowered_names
    ):
        raise ValidationAppError("DOCX structure is invalid")

    if any(marker.lower() in name for name in lowered_names for marker in _FORBIDDEN_DOCX_PARTS):
        raise ValidationAppError("DOCX contains macros or embedded active objects")


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
    if doc_type == "unknown":
        raise ValidationAppError("Unsupported document type")

    _basic_sanitization_scan(doc_type=doc_type, file_bytes=file_bytes)
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    doc_id = uuid.uuid4().hex
    temp_dir = Path(settings.upload_temp_dir) / doc_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / safe_name

    async with aiofiles.open(temp_path, "wb") as handle:
        await handle.write(file_bytes)

    return doc_id, str(temp_path), safe_name, mime_type, len(file_bytes), sha256, doc_type
