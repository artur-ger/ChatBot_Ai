from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class CoreApiUnavailable(Exception):
    pass


class CoreApiValidationError(Exception):
    pass


class CoreApiClient:
    def __init__(self) -> None:
        timeout = httpx.Timeout(settings.request_timeout_seconds)
        self._client = httpx.AsyncClient(
            base_url=settings.core_api_base_url.rstrip("/"),
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def send_message(self, *, chat_id: str, text: str) -> str:
        payload = {
            "chat_id": chat_id,
            "text": text,
        }

        data = await self._request_with_retries(
            "POST",
            "/chat",
            json=payload,
        )
        return str(data.get("text") or "Не удалось получить текст ответа от сервиса.")

    async def reset_chat(self, *, chat_id: str) -> int:
        data = await self._request_with_retries(
            "POST",
            f"/chat/{chat_id}/reset",
        )
        return int(data.get("deleted_messages") or 0)

    async def upload_document(self, *, path: Path) -> dict[str, Any]:
        content_type_by_suffix = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain"
        }

        content_type = content_type_by_suffix.get(path.suffix.lower())

        if content_type is None:
            raise CoreApiValidationError("Поддерживаются только PDF, DOCX, TXT.")

        with path.open("rb") as file:
            files = {
                "file": (path.name, file, content_type),
            }
            return await self._request_with_retries(
                "POST",
                "/documents",
                files=files,
            )

    async def get_indexing_task_status(self, *, task_id: str) -> dict[str, Any]:
        return await self._request_with_retries(
            "GET",
            f"/indexing-tasks/{task_id}",
        )

    async def get_document_status(self, *, document_id: str) -> dict[str, Any]:
        return await self._request_with_retries(
            "GET",
            f"/documents/{document_id}",
        )

    async def _request_with_retries(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                response = await self._client.request(method, url, **kwargs)

                if response.status_code >= 500:
                    raise CoreApiUnavailable(f"Core API returned {response.status_code}")

                if response.status_code >= 400:
                    try:
                        data = response.json()
                        message = data.get("message") or data.get("detail") or response.text
                    except Exception:
                        message = response.text
                    raise CoreApiValidationError(message)

                return dict(response.json())

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                last_error = exc

            except CoreApiUnavailable as exc:
                last_error = exc

            if attempt < 2:
                await asyncio.sleep(2**attempt)

        raise CoreApiUnavailable(str(last_error) if last_error else "Core API unavailable")