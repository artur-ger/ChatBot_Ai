from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.errors import ValidationAppError


def extract_text_from_file(*, path: Path, doc_type: str) -> str:
    if doc_type in {"text", "markdown"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    if doc_type == "pdf":
        reader = PdfReader(str(path))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages).strip()

    if doc_type == "docx":
        document = DocxDocument(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()

    raise ValidationAppError("Unsupported document type for text extraction")
