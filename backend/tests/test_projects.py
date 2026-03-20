"""
Tests for /api/projects/* endpoints (Fase 2).
Covers: CRUD, slug generation, auto-environments, permissions per role, audit logs.
"""
import pytest
from sqlalchemy import select

from app.models import AuditLog, Environment, Project
from tests.conftest import _make_user


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Fixtures: pre-created projects ───────────────────────────────────────────

async def _make_project(client, token: str, name: str, description: str = "") -> dict:
    resp = await client.post(
        "/api/projects",
        headers=auth(token),
        json={"name": name, "description": description},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── POST /api/projects ───────────────────────────────────────────────────────

class TestCreateProject:
    async def test_admin_creates_project(self, test_client, admin_user, admin_token):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "My App", "description": "A test project"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My App"
        assert data["slug"] == "my-app"
        assert data["description"] == "A test project"
        assert data["is_archived"] is False
        assert data["owner"]["id"] == admin_user.id

    async def test_editor_creates_project(self, test_client, editor_user, editor_token):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(editor_token),
            json={"name": "Editor Project"},
        )
        assert resp.status_code == 201
        assert resp.json()["owner"]["id"] == editor_user.id

    async def test_viewer_gets_403(self, test_client, viewer_user, viewer_token):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(viewer_token),
            json={"name": "Viewer Project"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_no_auth_gets_401(self, test_client):
        resp = await test_client.post(
            "/api/projects", json={"name": "Anon Project"}
        )
        assert resp.status_code == 401

    async def test_auto_creates_three_environments(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "Env Test"},
        )
        assert resp.status_code == 201
        envs = resp.json()["environments"]
        assert len(envs) == 3
        names = [e["name"] for e in envs]
        assert "development" in names
        assert "staging" in names
        assert "production" in names

    async def test_production_requires_approval(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "Approval Test"},
        )
        envs = {e["name"]: e for e in resp.json()["environments"]}
        assert envs["production"]["require_approval"] is True
        assert envs["development"]["require_approval"] is False
        assert envs["staging"]["require_approval"] is False

    async def test_slug_generation_spaces(self, test_client, admin_user, admin_token):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "My Cool Project"},
        )
        assert resp.json()["slug"] == "my-cool-project"

    async def test_slug_generation_special_chars(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "API & Backend!"},
        )
        slug = resp.json()["slug"]
        assert " " not in slug
        assert "&" not in slug
        assert "!" not in slug

    async def test_duplicate_name_returns_409(
        self, test_client, admin_user, admin_token
    ):
        await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "Dup Project"},
        )
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "Dup Project"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "DUPLICATE_RESOURCE"

    async def test_config_count_starts_at_zero(
        self, test_client, admin_user, admin_token
    ):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "Zero Count"},
        )
        for env in resp.json()["environments"]:
            assert env["config_count"] == 0

    async def test_creates_audit_log(
        self, test_client, admin_user, admin_token, db_session
    ):
        resp = await test_client.post(
            "/api/projects",
            headers=auth(admin_token),
            json={"name": "Audit Project"},
        )
        project_id = resp.json()["id"]
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "project_created",
                AuditLog.resource_id == project_id,
                AuditLog.user_id == admin_user.id,
            )
        )
        assert result.scalar_one_or_none() is not None


# ─── GET /api/projects ────────────────────────────────────────────────────────

class TestListProjects:
    async def test_admin_sees_all_projects(
        self, test_client, admin_user, editor_user, admin_token, editor_token
    ):
        await _make_project(test_client, admin_token, "Admin Project")
        await _make_project(test_client, editor_token, "Editor Project")
        resp = await test_client.get("/api/projects", headers=auth(admin_token))
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] == 2

    async def test_editor_sees_all_projects(
        self, test_client, admin_user, editor_user, admin_token, editor_token
    ):
        await _make_project(test_client, admin_token, "Admin Project")
        await _make_project(test_client, editor_token, "Editor Project")
        resp = await test_client.get("/api/projects", headers=auth(editor_token))
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] == 2

    async def test_viewer_sees_all_projects(
        self, test_client, admin_user, viewer_user, admin_token, viewer_token
    ):
        await _make_project(test_client, admin_token, "Some Project")
        resp = await test_client.get("/api/projects", headers=auth(viewer_token))
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] == 1

    async def test_no_auth_gets_401(self, test_client):
        resp = await test_client.get("/api/projects")
        assert resp.status_code == 401

    async def test_search_filter(self, test_client, admin_user, admin_token):
        await _make_project(test_client, admin_token, "Backend Service")
        await _make_project(test_client, admin_token, "Frontend App")
        resp = await test_client.get(
            "/api/projects?search=backend", headers=auth(admin_token)
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert "Backend" in data[0]["name"]

    async def test_is_archived_filter(self, test_client, admin_user, admin_token):
        proj = await _make_project(test_client, admin_token, "Active Project")
        await _make_project(test_client, admin_token, "Archived Project")
        # Archive second project
        proj2_id = (
            await test_client.get("/api/projects", headers=auth(admin_token))
        ).json()["data"][0]["id"]
        await test_client.put(
            f"/api/projects/{proj2_id}",
            headers=auth(admin_token),
            json={"is_archived": True},
        )
        resp = await test_client.get(
            "/api/projects?is_archived=false", headers=auth(admin_token)
        )
        assert all(not p["is_archived"] for p in resp.json()["data"])

    async def test_pagination(self, test_client, admin_user, admin_token):
        for i in range(5):
            await _make_project(test_client, admin_token, f"Project {i}")
        resp = await test_client.get(
            "/api/projects?page=1&per_page=3", headers=auth(admin_token)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 3
        assert body["pagination"]["total"] == 5
        assert body["pagination"]["pages"] == 2

    async def test_each_project_has_environments(
        self, test_client, admin_user, admin_token
    ):
        await _make_project(test_client, admin_token, "Env Project")
        resp = await test_client.get("/api/projects", headers=auth(admin_token))
        for project in resp.json()["data"]:
            assert len(project["environments"]) == 3


# ─── GET /api/projects/{id} ───────────────────────────────────────────────────

class TestGetProject:
    async def test_all_roles_can_get(
        self,
        test_client,
        admin_user, editor_user, viewer_user,
        admin_token, editor_token, viewer_token,
    ):
        proj = await _make_project(test_client, admin_token, "Shared Project")
        for token in (admin_token, editor_token, viewer_token):
            resp = await test_client.get(
                f"/api/projects/{proj['id']}", headers=auth(token)
            )
            assert resp.status_code == 200
            assert resp.json()["id"] == proj["id"]

    async def test_not_found_returns_404(self, test_client, admin_user, admin_token):
        resp = await test_client.get("/api/projects/99999", headers=auth(admin_token))
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "NOT_FOUND"

    async def test_no_auth_gets_401(self, test_client, admin_user, admin_token):
        proj = await _make_project(test_client, admin_token, "Auth Test")
        resp = await test_client.get(f"/api/projects/{proj['id']}")
        assert resp.status_code == 401


# ─── PUT /api/projects/{id} ───────────────────────────────────────────────────

class TestUpdateProject:
    async def test_admin_can_update_any_project(
        self, test_client, admin_user, editor_user, admin_token, editor_token
    ):
        proj = await _make_project(test_client, editor_token, "Editor Owned")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(admin_token),
            json={"name": "Admin Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Admin Renamed"
        assert resp.json()["slug"] == "admin-renamed"

    async def test_editor_can_update_own_project(
        self, test_client, editor_user, editor_token
    ):
        proj = await _make_project(test_client, editor_token, "My Project")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(editor_token),
            json={"description": "Updated description"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    async def test_editor_cannot_update_others_project(
        self, test_client, admin_user, editor_user, admin_token, editor_token
    ):
        proj = await _make_project(test_client, admin_token, "Admin Owned")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(editor_token),
            json={"name": "Stolen"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_viewer_gets_403(
        self, test_client, admin_user, viewer_user, admin_token, viewer_token
    ):
        proj = await _make_project(test_client, admin_token, "View Only")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(viewer_token),
            json={"name": "Hacked"},
        )
        assert resp.status_code == 403

    async def test_archive_project(self, test_client, admin_user, admin_token):
        proj = await _make_project(test_client, admin_token, "To Archive")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(admin_token),
            json={"is_archived": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_archived"] is True

    async def test_name_change_updates_slug(
        self, test_client, admin_user, admin_token
    ):
        proj = await _make_project(test_client, admin_token, "Old Name")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(admin_token),
            json={"name": "New Name Here"},
        )
        assert resp.json()["slug"] == "new-name-here"

    async def test_duplicate_name_returns_409(
        self, test_client, admin_user, admin_token
    ):
        await _make_project(test_client, admin_token, "Taken Name")
        proj = await _make_project(test_client, admin_token, "Other Project")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(admin_token),
            json={"name": "Taken Name"},
        )
        assert resp.status_code == 409

    async def test_not_found_returns_404(self, test_client, admin_user, admin_token):
        resp = await test_client.put(
            "/api/projects/99999",
            headers=auth(admin_token),
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404

    async def test_no_changes_returns_200(
        self, test_client, admin_user, admin_token
    ):
        proj = await _make_project(test_client, admin_token, "Stable")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(admin_token),
            json={},
        )
        assert resp.status_code == 200

    async def test_creates_audit_log(
        self, test_client, admin_user, admin_token, db_session
    ):
        proj = await _make_project(test_client, admin_token, "Audit Update")
        await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(admin_token),
            json={"description": "Changed"},
        )
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "project_updated",
                AuditLog.resource_id == proj["id"],
            )
        )
        assert result.scalar_one_or_none() is not None


# ─── DELETE /api/projects/{id} ────────────────────────────────────────────────

class TestDeleteProject:
    async def test_admin_can_delete(
        self, test_client, admin_user, admin_token, db_session
    ):
        proj = await _make_project(test_client, admin_token, "To Delete")
        project_id = proj["id"]

        resp = await test_client.delete(
            f"/api/projects/{project_id}", headers=auth(admin_token)
        )
        assert resp.status_code == 204

        # Verify project gone from DB
        result = await db_session.execute(
            select(Project).where(Project.id == project_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_cascade_deletes_environments(
        self, test_client, admin_user, admin_token, db_session
    ):
        proj = await _make_project(test_client, admin_token, "Cascade Test")
        project_id = proj["id"]
        env_ids = [e["id"] for e in proj["environments"]]

        await test_client.delete(
            f"/api/projects/{project_id}", headers=auth(admin_token)
        )

        for env_id in env_ids:
            result = await db_session.execute(
                select(Environment).where(Environment.id == env_id)
            )
            assert result.scalar_one_or_none() is None, f"Environment {env_id} not deleted"

    async def test_editor_gets_403(
        self, test_client, admin_user, editor_user, admin_token, editor_token
    ):
        proj = await _make_project(test_client, editor_token, "Editor Project")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}", headers=auth(editor_token)
        )
        assert resp.status_code == 403

    async def test_viewer_gets_403(
        self, test_client, admin_user, viewer_user, admin_token, viewer_token
    ):
        proj = await _make_project(test_client, admin_token, "View Project")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}", headers=auth(viewer_token)
        )
        assert resp.status_code == 403

    async def test_not_found_returns_404(self, test_client, admin_user, admin_token):
        resp = await test_client.delete(
            "/api/projects/99999", headers=auth(admin_token)
        )
        assert resp.status_code == 404

    async def test_creates_audit_log(
        self, test_client, admin_user, admin_token, db_session
    ):
        proj = await _make_project(test_client, admin_token, "Delete Audit")
        project_id = proj["id"]
        await test_client.delete(
            f"/api/projects/{project_id}", headers=auth(admin_token)
        )
        result = await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "project_deleted",
                AuditLog.resource_id == project_id,
            )
        )
        assert result.scalar_one_or_none() is not None
