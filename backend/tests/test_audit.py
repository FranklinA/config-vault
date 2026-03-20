"""
Tests for /api/audit/* endpoints (Fase 5).

Coverage:
  - GET /api/audit           — admin, filters (action/resource/user/project/dates), pagination
  - GET /api/audit/export    — admin, CSV format, filters
  - GET /api/projects/{id}/audit — admin all, editor-owner, editor-other 403, viewer allowed
"""
import csv
import io
import pytest
from sqlalchemy import select

from app.models import AuditLog


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Helpers to generate audit data ───────────────────────────────────────────

async def _make_project(client, token, name="Audit Test Project") -> dict:
    resp = await client.post("/api/projects", headers=auth(token), json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _make_config(client, token, project_id, env_id, key="AUDIT_KEY", value="v", config_type="string") -> dict:
    resp = await client.post(
        f"/api/projects/{project_id}/environments/{env_id}/configs",
        headers=auth(token),
        json={"key": key, "value": value, "config_type": config_type},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _dev_id(project):
    return next(e["id"] for e in project["environments"] if e["name"] == "development")

def _prod_id(project):
    return next(e["id"] for e in project["environments"] if e["name"] == "production")


@pytest.fixture
async def project_with_data(test_client, admin_token, editor_token):
    """Project with several audit-generating actions."""
    proj = await _make_project(test_client, admin_token, "Audit Data Project")
    dev = _dev_id(proj)
    prod = _prod_id(proj)

    # admin creates config
    cfg = await _make_config(test_client, admin_token, proj["id"], dev, key="DEV_VAR")

    # admin updates config
    await test_client.put(
        f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg['id']}",
        headers=auth(admin_token),
        json={"value": "updated"},
    )

    # editor creates approval in production
    await test_client.post(
        f"/api/projects/{proj['id']}/environments/{prod}/configs",
        headers=auth(editor_token),
        json={"key": "PROD_VAR", "value": "pv", "config_type": "string"},
    )

    return proj


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/audit
# ══════════════════════════════════════════════════════════════════════════════

class TestListAuditLogs:
    async def test_admin_can_list(self, test_client, project_with_data, admin_token):
        resp = await test_client.get("/api/audit", headers=auth(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body
        assert body["pagination"]["total"] > 0

    async def test_editor_gets_403(self, test_client, editor_token):
        resp = await test_client.get("/api/audit", headers=auth(editor_token))
        assert resp.status_code == 403

    async def test_viewer_gets_403(self, test_client, viewer_token):
        resp = await test_client.get("/api/audit", headers=auth(viewer_token))
        assert resp.status_code == 403

    async def test_unauthenticated_gets_401(self, test_client):
        resp = await test_client.get("/api/audit")
        assert resp.status_code == 401

    async def test_response_shape(self, test_client, project_with_data, admin_token):
        resp = await test_client.get("/api/audit", headers=auth(admin_token))
        item = resp.json()["data"][0]
        for field in ("id", "user", "action", "resource_type", "resource_id",
                      "project", "details", "ip_address", "created_at"):
            assert field in item
        assert "id" in item["user"]
        assert "name" in item["user"]

    async def test_filter_by_action(self, test_client, project_with_data, admin_token):
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"action": "config_created"},
        )
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(d["action"] == "config_created" for d in data)

    async def test_filter_by_resource_type(self, test_client, project_with_data, admin_token):
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"resource_type": "approval"},
        )
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(d["resource_type"] == "approval" for d in data)

    async def test_filter_by_project_id(self, test_client, project_with_data, admin_token):
        proj_id = project_with_data["id"]
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"project_id": proj_id},
        )
        data = resp.json()["data"]
        assert len(data) > 0
        # All logs reference this project
        for item in data:
            assert item["project"]["id"] == proj_id

    async def test_filter_by_user_id(self, test_client, project_with_data, admin_token, admin_user):
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"user_id": admin_user.id},
        )
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(d["user"]["id"] == admin_user.id for d in data)

    async def test_filter_by_date_from_excludes_old(self, test_client, project_with_data, admin_token):
        # Far-future date should return nothing
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"date_from": "2099-01-01T00:00:00"},
        )
        assert resp.json()["pagination"]["total"] == 0

    async def test_filter_by_date_to_excludes_future(self, test_client, project_with_data, admin_token):
        # Far-past date should return nothing
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"date_to": "2000-01-01T00:00:00"},
        )
        assert resp.json()["pagination"]["total"] == 0

    async def test_invalid_date_gets_422(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"date_from": "not-a-date"},
        )
        assert resp.status_code == 422

    async def test_pagination(self, test_client, project_with_data, admin_token):
        total = test_client  # just to use fixture
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"per_page": 2, "page": 1},
        )
        body = resp.json()
        assert len(body["data"]) <= 2
        assert body["pagination"]["per_page"] == 2

    async def test_all_required_actions_generated(self, test_client, project_with_data, admin_token):
        """Verifies that Fases 1-4 generated the expected audit action types."""
        resp = await test_client.get("/api/audit", headers=auth(admin_token), params={"per_page": 200})
        actions = {d["action"] for d in resp.json()["data"]}
        # These actions must have been generated by the fixture
        assert "config_created" in actions
        assert "config_updated" in actions
        assert "approval_requested" in actions

    async def test_details_is_parsed_json(self, test_client, project_with_data, admin_token):
        resp = await test_client.get(
            "/api/audit", headers=auth(admin_token),
            params={"action": "config_created"},
        )
        item = resp.json()["data"][0]
        assert isinstance(item["details"], dict)


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/audit/export
# ══════════════════════════════════════════════════════════════════════════════

class TestExportAuditLogs:
    async def test_returns_csv(self, test_client, project_with_data, admin_token):
        resp = await test_client.get("/api/audit/export", headers=auth(admin_token))
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")

    async def test_csv_has_header_row(self, test_client, project_with_data, admin_token):
        resp = await test_client.get("/api/audit/export", headers=auth(admin_token))
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert header == ["timestamp", "user", "action", "resource_type", "resource_id", "project", "details"]

    async def test_csv_has_data_rows(self, test_client, project_with_data, admin_token):
        resp = await test_client.get("/api/audit/export", headers=auth(admin_token))
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) > 1  # header + at least one data row

    async def test_csv_filter_by_action(self, test_client, project_with_data, admin_token):
        resp = await test_client.get(
            "/api/audit/export", headers=auth(admin_token),
            params={"action": "config_created"},
        )
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)[1:]  # skip header
        assert len(rows) > 0
        assert all(r[2] == "config_created" for r in rows)

    async def test_editor_gets_403(self, test_client, editor_token):
        resp = await test_client.get("/api/audit/export", headers=auth(editor_token))
        assert resp.status_code == 403

    async def test_empty_export_still_has_header(self, test_client, admin_token):
        resp = await test_client.get(
            "/api/audit/export", headers=auth(admin_token),
            params={"date_from": "2099-01-01"},
        )
        assert resp.status_code == 200
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert rows[0] == ["timestamp", "user", "action", "resource_type", "resource_id", "project", "details"]
        assert len(rows) == 1  # header only


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/projects/{id}/audit
# ══════════════════════════════════════════════════════════════════════════════

class TestProjectAuditLogs:
    async def test_admin_sees_project_logs(self, test_client, project_with_data, admin_token):
        proj_id = project_with_data["id"]
        resp = await test_client.get(f"/api/projects/{proj_id}/audit", headers=auth(admin_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(d["project"]["id"] == proj_id for d in data)

    async def test_editor_owner_can_see(self, test_client, admin_token, editor_token, editor_user):
        # Editor creates own project
        proj = await _make_project(test_client, editor_token, "Editor Own Project")
        dev = _dev_id(proj)
        await _make_config(test_client, editor_token, proj["id"], dev, key="E_KEY")

        resp = await test_client.get(f"/api/projects/{proj['id']}/audit", headers=auth(editor_token))
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] > 0

    async def test_editor_non_owner_gets_403(self, test_client, project_with_data, editor_token):
        # project_with_data is owned by admin, not editor
        proj_id = project_with_data["id"]
        resp = await test_client.get(f"/api/projects/{proj_id}/audit", headers=auth(editor_token))
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_viewer_can_see_project_audit(self, test_client, project_with_data, viewer_token):
        proj_id = project_with_data["id"]
        resp = await test_client.get(f"/api/projects/{proj_id}/audit", headers=auth(viewer_token))
        assert resp.status_code == 200

    async def test_project_not_found_gets_404(self, test_client, admin_token):
        resp = await test_client.get("/api/projects/99999/audit", headers=auth(admin_token))
        assert resp.status_code == 404

    async def test_unauthenticated_gets_401(self, test_client, project_with_data):
        proj_id = project_with_data["id"]
        resp = await test_client.get(f"/api/projects/{proj_id}/audit")
        assert resp.status_code == 401

    async def test_filter_by_action_in_project(self, test_client, project_with_data, admin_token):
        proj_id = project_with_data["id"]
        resp = await test_client.get(
            f"/api/projects/{proj_id}/audit", headers=auth(admin_token),
            params={"action": "config_updated"},
        )
        data = resp.json()["data"]
        assert len(data) > 0
        assert all(d["action"] == "config_updated" for d in data)

    async def test_pagination_project_audit(self, test_client, project_with_data, admin_token):
        proj_id = project_with_data["id"]
        resp = await test_client.get(
            f"/api/projects/{proj_id}/audit", headers=auth(admin_token),
            params={"per_page": 1, "page": 1},
        )
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["pagination"]["per_page"] == 1
