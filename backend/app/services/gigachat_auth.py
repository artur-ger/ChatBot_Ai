from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.errors import DependencyAppError, ValidationAppError
from app.core.secret_encryption import decrypt_secret
from app.repositories.llm_integration_repository import LlmIntegrationRepository

logger = logging.getLogger(__name__)

_REFRESH_LOOP_INTERVAL_SEC = 25 * 60


@dataclass(frozen=True)
class GigaChatAuthConfig:
    auth_url: str
    scope: str
    authorization_key: str | None
    client_id: str | None
    client_secret: str | None
    allow_unsafe_tls: bool
    refresh_margin_sec: float

    def cache_key(self) -> str:
        if self.authorization_key:
            return f"auth:{self.authorization_key[:32]}"
        return f"client:{self.client_id}:{self.client_secret or ''}"

    def has_credentials(self) -> bool:
        if self.authorization_key:
            return True
        return bool(self.client_id and self.client_secret)


def _normalize_basic_auth(value: str) -> str:
    normalized = value.strip().strip('"')
    return normalized if normalized.startswith("Basic ") else f"Basic {normalized}"


def _resolve_basic_auth(config: GigaChatAuthConfig) -> str:
    if config.authorization_key:
        return _normalize_basic_auth(config.authorization_key)
    if config.client_id and config.client_secret:
        import base64

        encoded = base64.b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
        return f"Basic {encoded}"
    raise ValidationAppError(
        "GigaChat OAuth credentials missing: укажите api_key (Basic ...) в интеграции LLM в админке"
    )


def build_gigachat_auth_config(
    *,
    authorization_key: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> GigaChatAuthConfig:
    return GigaChatAuthConfig(
        auth_url=settings.gigachat_auth_url,
        scope=settings.gigachat_scope,
        authorization_key=authorization_key,
        client_id=client_id,
        client_secret=client_secret,
        allow_unsafe_tls=settings.gigachat_allow_unsafe_tls,
        refresh_margin_sec=settings.gigachat_token_refresh_margin_sec,
    )


# Backward-compatible alias for tests and imports
build_auth_config_from_settings = build_gigachat_auth_config


class GigaChatTokenManager:
    def __init__(self, config: GigaChatAuthConfig) -> None:
        self._config = config
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._verify_tls = not config.allow_unsafe_tls

    @property
    def config(self) -> GigaChatAuthConfig:
        return self._config

    async def get_token(self, *, force: bool = False) -> str:
        now = time.time()
        margin = self._config.refresh_margin_sec
        if not force and self._access_token and now < self._expires_at - margin:
            return self._access_token

        async with self._lock:
            now = time.time()
            if not force and self._access_token and now < self._expires_at - margin:
                return self._access_token
            return await self._fetch_token()

    async def _fetch_token(self) -> str:
        basic_auth = _resolve_basic_auth(self._config)
        headers = {
            "Authorization": basic_auth,
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {"scope": self._config.scope}
        try:
            async with httpx.AsyncClient(verify=self._verify_tls) as client:
                response = await client.post(
                    self._config.auth_url,
                    headers=headers,
                    data=data,
                    timeout=settings.llm_timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise DependencyAppError("GigaChat OAuth request timed out") from exc
        except httpx.HTTPError as exc:
            raise DependencyAppError(f"GigaChat OAuth HTTP error: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text[:300]
            raise DependencyAppError(
                f"GigaChat OAuth failed: HTTP {response.status_code} {detail}"
            )

        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise DependencyAppError("GigaChat OAuth response missing access_token")

        expires_at_raw = float(payload.get("expires_at") or 0)
        expires_in = float(payload.get("expires_in") or 0)
        if expires_at_raw > 0:
            self._expires_at = expires_at_raw / 1000.0
        else:
            self._expires_at = time.time() + max(60.0, expires_in)

        self._access_token = access_token
        logger.debug(
            "GigaChat token refreshed, expires_at=%.0f margin_sec=%.0f",
            self._expires_at,
            self._config.refresh_margin_sec,
        )
        return access_token

    def invalidate(self) -> None:
        self._access_token = None
        self._expires_at = 0.0


_managers: dict[str, GigaChatTokenManager] = {}
_refresh_loop_task: asyncio.Task[None] | None = None


def get_gigachat_token_manager(
    *,
    authorization_key: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> GigaChatTokenManager:
    config = build_gigachat_auth_config(
        authorization_key=authorization_key,
        client_id=client_id,
        client_secret=client_secret,
    )
    if not config.has_credentials():
        raise ValidationAppError(
            "GigaChat OAuth credentials missing: укажите api_key (Basic ...) в интеграции LLM в админке"
        )
    cache_key = config.cache_key()
    manager = _managers.get(cache_key)
    if manager is None:
        manager = GigaChatTokenManager(config)
        _managers[cache_key] = manager
    return manager


async def warm_active_gigachat_integration(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        row = await LlmIntegrationRepository(session).get_active()
    if row is None or row.provider != "gigachat" or not row.api_key_encrypted:
        return
    api_key = decrypt_secret(row.api_key_encrypted)
    try:
        await get_gigachat_token_manager(authorization_key=api_key).get_token(force=True)
    except Exception:
        logger.warning("GigaChat warm-up for active integration failed", exc_info=True)


async def _refresh_loop() -> None:
    while True:
        await asyncio.sleep(_REFRESH_LOOP_INTERVAL_SEC)
        for manager in list(_managers.values()):
            try:
                await manager.get_token(force=True)
            except Exception:
                logger.warning("Scheduled GigaChat token refresh failed", exc_info=True)


def start_gigachat_token_refresh_loop() -> asyncio.Task[None]:
    global _refresh_loop_task
    if _refresh_loop_task is not None and not _refresh_loop_task.done():
        return _refresh_loop_task

    _refresh_loop_task = asyncio.create_task(_refresh_loop(), name="gigachat-token-refresh")
    return _refresh_loop_task


async def stop_gigachat_token_refresh_loop() -> None:
    global _refresh_loop_task
    if _refresh_loop_task is None:
        return
    _refresh_loop_task.cancel()
    try:
        await _refresh_loop_task
    except asyncio.CancelledError:
        pass
    _refresh_loop_task = None


def reset_gigachat_managers_for_tests() -> None:
    global _refresh_loop_task
    _managers.clear()
    _refresh_loop_task = None
