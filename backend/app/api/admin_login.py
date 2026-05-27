import hmac

from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.admin_auth import _make_admin_session_cookie
from app.core.config import settings
from app.core.limiter import limiter
from app.core.errors import AppError
from app.schemas.chat import ErrorResponse


router = APIRouter(prefix="/admin", tags=["admin-auth"])


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login", status_code=200)
@limiter.limit("20/minute")
async def login(request: Request, body: AdminLoginRequest = Body(...)) -> JSONResponse:
    if settings.admin_api_auth_disabled:
        # Auth disabled: still allow "login" but do not create a session cookie.
        return JSONResponse(content={"ok": True})

    expected_user = settings.admin_username
    expected_pass = settings.admin_password
    if not expected_user or not expected_pass:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "admin_credentials_not_configured",
                "message": "ADMIN_USERNAME/ADMIN_PASSWORD are not configured",
                "retry_allowed": True,
            },
        )

    if not hmac.compare_digest(body.username, expected_user) or not hmac.compare_digest(
        body.password, expected_pass
    ):
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "unauthorized",
                "message": "Invalid username or password",
                "retry_allowed": False,
            },
        )

    session_cookie = _make_admin_session_cookie(username=body.username)
    response = JSONResponse(content={"ok": True})
    response.set_cookie(
        key=settings.admin_session_cookie_name,
        value=session_cookie,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/logout", status_code=200)
@limiter.limit("20/minute")
async def logout(request: Request) -> JSONResponse:
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(key=settings.admin_session_cookie_name, path="/")
    return response

