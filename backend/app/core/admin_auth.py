from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Cookie, Header, HTTPException, status

from app.core.config import settings


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _make_admin_session_cookie(*, username: str) -> str:
    secret = settings.admin_session_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "admin_session_secret_not_configured",
                "message": "ADMIN_SESSION_SECRET is not configured",
                "retry_allowed": True,
            },
        )

    exp = int(time.time()) + int(settings.admin_session_ttl_sec)
    payload = {"sub": username, "exp": exp}
    payload_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload_raw)
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify_admin_session_cookie(*, cookie_value: str) -> str:
    secret = settings.admin_session_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "unauthorized",
                "message": "Admin session is not configured",
                "retry_allowed": False,
            },
        )

    try:
        payload_b64, sig_hex = cookie_value.split(".", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "unauthorized",
                "message": "Invalid admin session cookie",
                "retry_allowed": False,
            },
        ) from exc

    expected_sig = hmac.new(
        secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig_hex, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "unauthorized",
                "message": "Invalid admin session signature",
                "retry_allowed": False,
            },
        )

    payload_raw = _b64url_decode(payload_b64)
    payload = json.loads(payload_raw.decode("utf-8"))
    exp = int(payload.get("exp") or 0)
    username = str(payload.get("sub") or "")
    if not username or exp < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "unauthorized",
                "message": "Admin session expired",
                "retry_allowed": True,
            },
        )
    return username


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    if settings.admin_api_auth_disabled:
        return

    expected = settings.admin_api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "admin_auth_not_configured",
                "message": "ADMIN_API_TOKEN is not configured",
                "retry_allowed": False,
            },
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "unauthorized",
                "message": "Missing or invalid Authorization header",
                "retry_allowed": False,
            },
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "unauthorized",
                "message": "Invalid admin token",
                "retry_allowed": False,
            },
        )


def require_admin_auth(
    authorization: str | None = Header(default=None),
    admin_session: str | None = Cookie(default=None, alias="admin_session"),
) -> None:
    """
    Admin access via either:
    - Authorization: Bearer ADMIN_API_TOKEN (legacy/scripts)
    - HttpOnly cookie admin_session (login/password)
    """
    if settings.admin_api_auth_disabled:
        return

    expected_token = settings.admin_api_token
    if expected_token and authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if hmac.compare_digest(token, expected_token):
            return

    cookie_name = settings.admin_session_cookie_name
    if not admin_session and cookie_name:
        # FastAPI will not map Cookie alias=None reliably; this fallback ensures we still fail closed.
        admin_session = None

    if admin_session:
        _verify_admin_session_cookie(cookie_value=admin_session)
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error_code": "unauthorized",
            "message": "Missing or invalid admin session",
            "retry_allowed": False,
        },
    )
