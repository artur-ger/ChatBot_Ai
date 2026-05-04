from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_critical_alert(*, title: str, details: str) -> None:
    if not settings.alert_webhook_url:
        return
    payload = {"title": title, "details": details}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(settings.alert_webhook_url, json=payload)
    except Exception:
        logger.exception("Failed to send alert webhook")
