from __future__ import annotations

import app.core.admin_auth as admin_auth_module
import app.core.config as config_module
import app.api.admin_login as admin_login_module


def test_documents_require_admin_when_auth_enabled(client, monkeypatch):
    old_settings = config_module.settings
    old_admin_auth_settings = admin_auth_module.settings

    try:
        monkeypatch.setenv("ADMIN_API_AUTH_DISABLED", "false")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret-admin-token")

        patched_settings = config_module.Settings()
        config_module.settings = patched_settings
        admin_auth_module.settings = patched_settings

        files = {"file": ("note.txt", b"secret upload", "text/plain")}

        denied = client.post("/api/v1/documents", files=files)
        assert denied.status_code == 401

        allowed = client.post(
            "/api/v1/documents",
            files=files,
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert allowed.status_code == 202, allowed.text
    finally:
        config_module.settings = old_settings
        admin_auth_module.settings = old_admin_auth_settings


def test_ui_config_endpoint(client):
    response = client.get("/system/ui-config")
    assert response.status_code == 200
    payload = response.json()
    assert "show_admin_link" in payload
    assert "chat_acl_required" in payload
    # В тестовой конфигации `CHAT_ACL_DISABLED=true`
    assert payload["chat_acl_required"] is False


def test_admin_reindex_requires_token_when_auth_enabled(client, monkeypatch):
    old_settings = config_module.settings
    old_admin_auth_settings = admin_auth_module.settings

    try:
        monkeypatch.setenv("ADMIN_API_AUTH_DISABLED", "false")
        monkeypatch.setenv("ADMIN_API_TOKEN", "secret-admin-token")

        patched_settings = config_module.Settings()
        config_module.settings = patched_settings
        admin_auth_module.settings = patched_settings

        payload = {
            "from_embedding_version": "v1",
            "to_embedding_version": "v2",
        }
        denied = client.post("/api/v1/admin/reindex", json=payload)
        assert denied.status_code == 401

        allowed = client.post(
            "/api/v1/admin/reindex",
            json=payload,
            headers={"Authorization": "Bearer secret-admin-token"},
        )
        assert allowed.status_code == 202, allowed.text
    finally:
        config_module.settings = old_settings
        admin_auth_module.settings = old_admin_auth_settings


def test_admin_login_sets_cookie_and_allows_access(client, monkeypatch):
    old_settings = config_module.settings
    old_admin_auth_settings = admin_auth_module.settings
    old_admin_login_settings = admin_login_module.settings

    try:
        monkeypatch.setenv("ADMIN_API_AUTH_DISABLED", "false")
        monkeypatch.setenv("ADMIN_USERNAME", "admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "pass123")
        monkeypatch.setenv("ADMIN_SESSION_SECRET", "test-session-secret")

        patched_settings = config_module.Settings()
        config_module.settings = patched_settings
        admin_auth_module.settings = patched_settings
        admin_login_module.settings = patched_settings

        login = client.post(
            "/api/v1/admin/login",
            json={"username": "admin", "password": "pass123"},
        )
        assert login.status_code == 200, login.text
        # TestClient должен отправлять cookie в последующих запросах.
        allowed = client.get("/api/v1/documents?limit=1")
        assert allowed.status_code == 200, allowed.text
    finally:
        config_module.settings = old_settings
        admin_auth_module.settings = old_admin_auth_settings
        admin_login_module.settings = old_admin_login_settings

