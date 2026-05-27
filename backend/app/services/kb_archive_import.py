from __future__ import annotations

import hashlib
import os
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import aiofiles
import yaml

from app.core.config import settings
from app.core.errors import ValidationAppError


@dataclass(frozen=True)
class KbArchiveEntry:
    document_id: str
    source_path: str
    original_filename: str
    temp_path: str
    size_bytes: int
    sha256: str
    doc_type: str


def _normalize_zip_path(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValidationAppError("Archive contains unsafe paths")
    return normalized.as_posix()


def _read_yaml(zip_file: zipfile.ZipFile, path: str) -> dict[str, Any]:
    try:
        raw = zip_file.read(path)
    except KeyError as exc:
        raise ValidationAppError(f"Manifest file not found: {path}") from exc
    data = yaml.safe_load(raw.decode("utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ValidationAppError(f"Manifest must be an object: {path}")
    return data


def _doc_type_from_manifest(value: object, source_path: str) -> str:
    manifest_type = str(value or "").strip().lower()
    if manifest_type in {"markdown", "text"}:
        return manifest_type
    lower = source_path.lower()
    if lower.endswith((".md", ".markdown")):
        return "markdown"
    if lower.endswith(".txt"):
        return "text"
    raise ValidationAppError(f"Unsupported KB source type: {source_path}")


def _collect_docs(
    zip_file: zipfile.ZipFile,
    manifest_path: str,
    seen_manifests: set[str],
) -> list[tuple[str, dict[str, Any], str]]:
    manifest_path = _normalize_zip_path(manifest_path)
    if manifest_path in seen_manifests:
        return []
    seen_manifests.add(manifest_path)

    manifest = _read_yaml(zip_file, manifest_path)
    manifest_dir = PurePosixPath(manifest_path).parent
    entries: list[tuple[str, dict[str, Any], str]] = []

    imports = manifest.get("imports") or []
    if not isinstance(imports, list):
        raise ValidationAppError(f"imports must be a list: {manifest_path}")
    for import_path_raw in imports:
        import_path = _normalize_zip_path((manifest_dir / str(import_path_raw)).as_posix())
        entries.extend(_collect_docs(zip_file, import_path, seen_manifests))

    docs = manifest.get("docs") or {}
    if not isinstance(docs, dict):
        raise ValidationAppError(f"docs must be an object: {manifest_path}")
    for document_id, spec in docs.items():
        if not isinstance(spec, dict):
            raise ValidationAppError(f"Document spec must be an object: {document_id}")
        entries.append((str(document_id), spec, manifest_path))

    return entries


async def parse_kb_archive(
    *,
    filename: str,
    declared_content_type: str | None,
    file_bytes: bytes,
) -> list[KbArchiveEntry]:
    safe_name = os.path.basename(filename).strip().lower()
    if not safe_name.endswith(".zip"):
        raise ValidationAppError("KB archive must be a .zip file")
    if declared_content_type not in {
        None,
        "",
        "application/zip",
        "application/x-zip-compressed",
        "application/octet-stream",
    }:
        raise ValidationAppError("KB archive MIME type is not allowed")
    if len(file_bytes) > settings.max_upload_bytes:
        raise ValidationAppError("KB archive is too large")

    import io

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise ValidationAppError("Invalid KB archive") from exc

    with zip_file:
        names = {_normalize_zip_path(name) for name in zip_file.namelist()}
        if "root.yaml" not in names:
            raise ValidationAppError("KB archive must contain root.yaml")

        manifest_docs = _collect_docs(zip_file, "root.yaml", set())
        if not manifest_docs:
            raise ValidationAppError("KB archive does not contain documents")
        if len(manifest_docs) > 500:
            raise ValidationAppError("KB archive contains too many documents")

        entries: list[KbArchiveEntry] = []
        total_unpacked_bytes = 0
        for document_id, spec, manifest_path in manifest_docs:
            source = spec.get("source")
            if not source:
                continue
            manifest_dir = PurePosixPath(manifest_path).parent
            source_path = _normalize_zip_path((manifest_dir / str(source)).as_posix())
            if source_path.startswith("__MACOSX/") or source_path not in names:
                raise ValidationAppError(f"KB source file not found: {source_path}")

            raw = zip_file.read(source_path)
            total_unpacked_bytes += len(raw)
            if total_unpacked_bytes > settings.max_upload_bytes * 10:
                raise ValidationAppError("KB archive unpacked content is too large")

            doc_type = _doc_type_from_manifest(spec.get("type"), source_path)
            temp_dir = Path(settings.upload_temp_dir) / document_id
            temp_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(temp_dir, 0o777)
            temp_path = temp_dir / Path(source_path).name
            async with aiofiles.open(temp_path, "wb") as handle:
                await handle.write(raw)
            os.chmod(temp_path, 0o666)

            entries.append(
                KbArchiveEntry(
                    document_id=document_id[:64],
                    source_path=source_path,
                    original_filename=source_path,
                    temp_path=str(temp_path),
                    size_bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),
                    doc_type=doc_type,
                )
            )

    if not entries:
        raise ValidationAppError("KB archive does not contain importable documents")
    return entries


def new_task_id() -> str:
    return uuid.uuid4().hex
