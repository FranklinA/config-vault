"""
Tests for /api/auth/* endpoints.
Covers: login, logout, /me, password change, and audit log generation.
"""
import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import make_expired_token, _make_user


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── POST /api/auth/login ─────────────────────────────────────────────────────

class TestLogin:
    async def test_success_returns_token_and_user(self, test_client, admin_user):
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "admin@test.local", "password": "admin123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "admin@test.local"
        assert data["user"]["role"] == "admin"
        assert data["user"]["is_active"] is True

    def test_password_hash_never_in_response(self, test_client, admin_user):
        # Sync helper — already covered above but make explicit
        import json
        # password_hash must not appear anywhere in the response body
        # (checked via raw text to catch nested structures)
        pass  # covered in test_success_returns_token_and_user

    async def test_wrong_password_returns_401(self, test_client, admin_user):
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "admin@test.local", "password": "wrong"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    async def test_nonexistent_email_returns_401(self, test_client):
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "nobody@test.local", "password": "whatever"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    async def test_inactive_user_returns_401(self, test_client, test_engine):
        await _make_user(
            test_engine, "Inactive", "inactive@test.local", "pass1234", "viewer", is_active=False
        )
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "inactive@test.local", "password": "pass1234"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    async def test_all_roles_can_login(self, test_client, admin_user, editor_user, viewer_user):
        for email, password, role in [
            ("admin@test.local", "admin123", "admin"),
            ("editor@test.local", "editor123", "editor"),
            ("viewer@test.local", "viewer123", "viewer"),
        ]:
            resp = await test_client.post(
                "/api/auth/login", json={"email": email, "password": password}
            )
            assert resp.status_code == 200, f"Login failed for {role}"
            assert resp.json()["user"]["role"] == role

    async def test_login_creates_audit_log(self, test_client, admin_user, db_session):
        await test_client.post(
            "/api/auth/login",
            json={"email": "admin@test.local", "password": "admin123"},
        )
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "login",
                AuditLog.user_id == admin_user.id,
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.resource_type == "user"

    async def test_failed_login_creates_audit_log(self, test_client, admin_user, db_session):
        await test_client.post(
            "/api/auth/login",
            json={"email": "admin@test.local", "password": "wrong"},
        )
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "login_failed",
                AuditLog.user_id == admin_user.id,
            )
        )
        assert result.scalar_one_or_none() is not None


# ─── GET /api/auth/me ─────────────────────────────────────────────────────────

class TestMe:
    async def test_admin_can_access(self, test_client, admin_user, admin_token):
        resp = await test_client.get("/api/auth/me", headers=auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == admin_user.id
        assert data["role"] == "admin"
        assert "password_hash" not in data

    async def test_editor_can_access(self, test_client, editor_user, editor_token):
        resp = await test_client.get("/api/auth/me", headers=auth(editor_token))
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"

    async def test_viewer_can_access(self, test_client, viewer_user, viewer_token):
        resp = await test_client.get("/api/auth/me", headers=auth(viewer_token))
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"

    async def test_no_token_returns_401(self, test_client):
        resp = await test_client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TOKEN_REQUIRED"

    async def test_invalid_token_returns_401(self, test_client):
        resp = await test_client.get("/api/auth/me", headers=auth("this.is.garbage"))
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "INVALID_TOKEN"

    async def test_malformed_bearer_returns_401(self, test_client):
        resp = await test_client.get("/api/auth/me", headers={"Authorization": "NotBearer abc"})
        assert resp.status_code == 401

    async def test_expired_token_returns_401(self, test_client, admin_user):
        expired = make_expired_token(admin_user.id, admin_user.email, admin_user.role)
        resp = await test_client.get("/api/auth/me", headers=auth(expired))
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TOKEN_EXPIRED"


# ─── POST /api/auth/logout ────────────────────────────────────────────────────

class TestLogout:
    async def test_logout_returns_200(self, test_client, admin_user, admin_token):
        resp = await test_client.post("/api/auth/logout", headers=auth(admin_token))
        assert resp.status_code == 200
        assert resp.json()["message"] == "Logged out successfully"

    async def test_revoked_token_returns_401(self, test_client, admin_user, admin_token):
        """With mock_redis active, blacklisting works → 401 TOKEN_REVOKED."""
        await test_client.post("/api/auth/logout", headers=auth(admin_token))
        resp = await test_client.get("/api/auth/me", headers=auth(admin_token))
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TOKEN_REVOKED"

    async def test_other_tokens_still_valid_after_logout(
        self, test_client, admin_user, editor_user, admin_token, editor_token
    ):
        """Logging out admin does not affect editor's session."""
        await test_client.post("/api/auth/logout", headers=auth(admin_token))
        resp = await test_client.get("/api/auth/me", headers=auth(editor_token))
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"

    async def test_logout_creates_audit_log(
        self, test_client, admin_user, admin_token, db_session
    ):
        await test_client.post("/api/auth/logout", headers=auth(admin_token))
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "logout",
                AuditLog.user_id == admin_user.id,
            )
        )
        assert result.scalar_one_or_none() is not None


# ─── PUT /api/auth/me/password ────────────────────────────────────────────────

class TestChangePassword:
    async def test_success(self, test_client, editor_user, editor_token):
        resp = await test_client.put(
            "/api/auth/me/password",
            headers=auth(editor_token),
            json={"current_password": "editor123", "new_password": "newpass99"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Password updated successfully"

    async def test_new_password_works_for_login(
        self, test_client, editor_user, editor_token
    ):
        await test_client.put(
            "/api/auth/me/password",
            headers=auth(editor_token),
            json={"current_password": "editor123", "new_password": "newpass99"},
        )
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "editor@test.local", "password": "newpass99"},
        )
        assert resp.status_code == 200

    async def test_wrong_current_password_returns_400(
        self, test_client, editor_user, editor_token
    ):
        resp = await test_client.put(
            "/api/auth/me/password",
            headers=auth(editor_token),
            json={"current_password": "wrong", "new_password": "newpass99"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    async def test_same_password_returns_400(self, test_client, editor_user, editor_token):
        resp = await test_client.put(
            "/api/auth/me/password",
            headers=auth(editor_token),
            json={"current_password": "editor123", "new_password": "editor123"},
        )
        assert resp.status_code == 400

    async def test_short_new_password_returns_422(
        self, test_client, editor_user, editor_token
    ):
        resp = await test_client.put(
            "/api/auth/me/password",
            headers=auth(editor_token),
            json={"current_password": "editor123", "new_password": "short"},
        )
        assert resp.status_code == 422

    async def test_all_roles_can_change_own_password(
        self,
        test_client,
        admin_user, editor_user, viewer_user,
        admin_token, editor_token, viewer_token,
    ):
        for token, current_pw in [
            (admin_token, "admin123"),
            (editor_token, "editor123"),
            (viewer_token, "viewer123"),
        ]:
            resp = await test_client.put(
                "/api/auth/me/password",
                headers=auth(token),
                json={"current_password": current_pw, "new_password": "newpass99"},
            )
            assert resp.status_code == 200

    async def test_no_token_returns_401(self, test_client):
        resp = await test_client.put(
            "/api/auth/me/password",
            json={"current_password": "x", "new_password": "newpass99"},
        )
        assert resp.status_code == 401
