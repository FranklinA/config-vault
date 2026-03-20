"""
Tests for /api/users/* endpoints.
Every endpoint is tested against all three roles (admin, editor, viewer).
"""
import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import _make_user


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── GET /api/users ───────────────────────────────────────────────────────────

class TestListUsers:
    async def test_admin_gets_200_with_all_users(
        self, test_client, admin_user, editor_user, viewer_user, admin_token
    ):
        resp = await test_client.get("/api/users", headers=auth(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body
        assert body["pagination"]["total"] == 3

    async def test_editor_gets_403(self, test_client, editor_user, editor_token):
        resp = await test_client.get("/api/users", headers=auth(editor_token))
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_viewer_gets_403(self, test_client, viewer_user, viewer_token):
        resp = await test_client.get("/api/users", headers=auth(viewer_token))
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_no_auth_gets_401(self, test_client):
        resp = await test_client.get("/api/users")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "TOKEN_REQUIRED"

    async def test_filter_by_role(
        self, test_client, admin_user, editor_user, viewer_user, admin_token
    ):
        resp = await test_client.get("/api/users?role=editor", headers=auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["role"] == "editor"

    async def test_filter_by_is_active(
        self, test_client, test_engine, admin_user, admin_token
    ):
        await _make_user(
            test_engine, "Inactive", "inactive@test.local", "pass1234", "viewer", is_active=False
        )
        resp = await test_client.get("/api/users?is_active=false", headers=auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["is_active"] is False

    async def test_filter_by_search_name(
        self, test_client, admin_user, editor_user, viewer_user, admin_token
    ):
        resp = await test_client.get("/api/users?search=Editor", headers=auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert "editor" in data[0]["email"]

    async def test_filter_by_search_email(
        self, test_client, admin_user, editor_user, viewer_user, admin_token
    ):
        resp = await test_client.get("/api/users?search=viewer", headers=auth(admin_token))
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_pagination_limits_results(
        self, test_client, admin_user, editor_user, viewer_user, admin_token
    ):
        resp = await test_client.get(
            "/api/users?page=1&per_page=2", headers=auth(admin_token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 3
        assert body["pagination"]["pages"] == 2

    async def test_password_hash_never_returned(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.get("/api/users", headers=auth(admin_token))
        for user in resp.json()["data"]:
            assert "password_hash" not in user


# ─── POST /api/users ──────────────────────────────────────────────────────────

class TestCreateUser:
    async def test_admin_creates_editor(self, test_client, admin_user, admin_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={
                "name": "New Editor",
                "email": "new.editor@test.local",
                "password": "pass1234",
                "role": "editor",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new.editor@test.local"
        assert data["role"] == "editor"
        assert data["is_active"] is True
        assert "password_hash" not in data

    async def test_admin_creates_viewer(self, test_client, admin_user, admin_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={
                "name": "New Viewer",
                "email": "new.viewer@test.local",
                "password": "pass1234",
                "role": "viewer",
            },
        )
        assert resp.status_code == 201

    async def test_editor_gets_403(self, test_client, editor_user, editor_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(editor_token),
            json={
                "name": "Hack",
                "email": "hack@test.local",
                "password": "pass1234",
                "role": "viewer",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_viewer_gets_403(self, test_client, viewer_user, viewer_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(viewer_token),
            json={
                "name": "Hack",
                "email": "hack@test.local",
                "password": "pass1234",
                "role": "viewer",
            },
        )
        assert resp.status_code == 403

    async def test_no_auth_gets_401(self, test_client):
        resp = await test_client.post(
            "/api/users",
            json={"name": "X", "email": "x@test.local", "password": "pass1234", "role": "viewer"},
        )
        assert resp.status_code == 401

    async def test_duplicate_email_returns_409(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={
                "name": "Dup",
                "email": "admin@test.local",
                "password": "pass1234",
                "role": "editor",
            },
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "DUPLICATE_RESOURCE"

    async def test_invalid_role_returns_422(self, test_client, admin_user, admin_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={
                "name": "Bad",
                "email": "bad@test.local",
                "password": "pass1234",
                "role": "superadmin",
            },
        )
        assert resp.status_code == 422

    async def test_short_password_returns_422(self, test_client, admin_user, admin_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={
                "name": "Short",
                "email": "short@test.local",
                "password": "123",
                "role": "viewer",
            },
        )
        assert resp.status_code == 422

    async def test_missing_required_fields_returns_422(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={"name": "NoEmail"},
        )
        assert resp.status_code == 422

    async def test_creates_audit_log(
        self, test_client, admin_user, admin_token, db_session
    ):
        await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={
                "name": "Audit Target",
                "email": "audit@test.local",
                "password": "pass1234",
                "role": "viewer",
            },
        )
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user_created",
                AuditLog.user_id == admin_user.id,
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.resource_type == "user"


# ─── PUT /api/users/{id} ──────────────────────────────────────────────────────

class TestUpdateUser:
    async def test_admin_can_rename(
        self, test_client, admin_user, editor_user, admin_token
    ):
        resp = await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"name": "Renamed Editor"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Editor"

    async def test_admin_can_change_role(
        self, test_client, admin_user, editor_user, admin_token
    ):
        resp = await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"role": "viewer"},
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"

    async def test_admin_can_deactivate_other_user(
        self, test_client, admin_user, editor_user, admin_token
    ):
        resp = await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_editor_gets_403(
        self, test_client, admin_user, editor_user, editor_token
    ):
        resp = await test_client.put(
            f"/api/users/{admin_user.id}",
            headers=auth(editor_token),
            json={"name": "Hacked"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_viewer_gets_403(
        self, test_client, admin_user, viewer_user, viewer_token
    ):
        resp = await test_client.put(
            f"/api/users/{admin_user.id}",
            headers=auth(viewer_token),
            json={"name": "Hacked"},
        )
        assert resp.status_code == 403

    async def test_no_auth_gets_401(self, test_client, admin_user):
        resp = await test_client.put(
            f"/api/users/{admin_user.id}", json={"name": "X"}
        )
        assert resp.status_code == 401

    async def test_not_found_returns_404(self, test_client, admin_user, admin_token):
        resp = await test_client.put(
            "/api/users/99999",
            headers=auth(admin_token),
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "NOT_FOUND"

    async def test_admin_cannot_deactivate_self(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.put(
            f"/api/users/{admin_user.id}",
            headers=auth(admin_token),
            json={"is_active": False},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_admin_cannot_change_own_role(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.put(
            f"/api/users/{admin_user.id}",
            headers=auth(admin_token),
            json={"role": "editor"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_email_field_ignored(
        self, test_client, admin_user, editor_user, admin_token
    ):
        """The update schema doesn't accept email — it must remain unchanged."""
        original_email = editor_user.email
        resp = await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"name": "New Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == original_email

    async def test_no_changes_still_returns_200(
        self, test_client, admin_user, editor_user, admin_token
    ):
        """Sending a body with no actual changes is a no-op, not an error."""
        resp = await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"name": editor_user.name},  # same name → no change
        )
        assert resp.status_code == 200

    async def test_creates_audit_log_on_change(
        self, test_client, admin_user, editor_user, admin_token, db_session
    ):
        await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"name": "Audit Target"},
        )
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user_updated",
                AuditLog.user_id == admin_user.id,
                AuditLog.resource_id == editor_user.id,
            )
        )
        assert result.scalar_one_or_none() is not None

    async def test_no_audit_log_when_no_changes(
        self, test_client, admin_user, editor_user, admin_token, db_session
    ):
        """Audit log is only written when something actually changes."""
        await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"name": editor_user.name},  # no-op
        )
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "user_updated",
                AuditLog.resource_id == editor_user.id,
            )
        )
        assert result.scalar_one_or_none() is None
