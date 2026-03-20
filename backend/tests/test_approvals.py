"""
Tests for /api/approvals/* endpoints (Fase 4).

Coverage:
  - GET    /api/approvals           — admin sees all, editor sees own, viewer 403
  - GET    /api/approvals/{id}      — admin, editor-own, editor-other 403
  - POST   /api/approvals/{id}/approve — admin applies change (create/update/delete)
  - POST   /api/approvals/{id}/reject  — admin rejects, change NOT applied
  - POST   /api/approvals/{id}/cancel  — editor cancels own, not others

Full flow tested: create approval → approve → verify config exists in DB
"""
import pytest
from sqlalchemy import select

from app.models import AuditLog, ConfigEntry
from tests.conftest import _make_user


# ─── Helpers ──────────────────────────────────────────────────────────────────

def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_project(client, token: str, name: str = "Approval Test Project") -> dict:
    resp = await client.post("/api/projects", headers=auth(token), json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _env_id(project: dict, env_name: str) -> int:
    for e in project["environments"]:
        if e["name"] == env_name:
            return e["id"]
    raise ValueError(f"Environment {env_name!r} not found")


def _configs_url(project_id: int, env_id: int) -> str:
    return f"/api/projects/{project_id}/environments/{env_id}/configs"


async def _make_config_direct(client, token, project_id, env_id, *, key, value="val", config_type="string") -> dict:
    """Create a config directly (admin) — returns ConfigEntryResponse."""
    resp = await client.post(
        _configs_url(project_id, env_id),
        headers=auth(token),
        json={"key": key, "value": value, "config_type": config_type},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _make_approval(client, token, project_id, env_id, *, key, value="val", config_type="string") -> dict:
    """Editor creates config in production → returns approval_request dict."""
    resp = await client.post(
        _configs_url(project_id, env_id),
        headers=auth(token),
        json={"key": key, "value": value, "config_type": config_type},
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["approval_request"]


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def project(test_client, admin_token):
    return await _make_project(test_client, admin_token)


@pytest.fixture
async def pending_approval(test_client, project, editor_token):
    """One pending approval for PROD_KEY in production."""
    prod_id = _env_id(project, "production")
    return await _make_approval(test_client, editor_token, project["id"], prod_id, key="PROD_KEY")


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/approvals
# ══════════════════════════════════════════════════════════════════════════════

class TestListApprovals:
    async def test_admin_sees_all(self, test_client, project, admin_token, editor_token):
        prod_id = _env_id(project, "production")
        await _make_approval(test_client, editor_token, project["id"], prod_id, key="K1")
        await _make_approval(test_client, editor_token, project["id"], prod_id, key="K2")

        resp = await test_client.get("/api/approvals", headers=auth(admin_token))
        assert resp.status_code == 200
        assert resp.json()["pagination"]["total"] == 2

    async def test_editor_sees_only_own(
        self, test_client, project, admin_token, editor_token, test_engine
    ):
        prod_id = _env_id(project, "production")
        # editor creates one
        await _make_approval(test_client, editor_token, project["id"], prod_id, key="E_KEY")
        # another editor creates one
        other = await _make_user(test_engine, "Other Editor", "other@test.local", "pass1234", "editor")
        from app.security import create_access_token
        other_token = create_access_token(other.id, other.email, other.role)
        await _make_approval(test_client, other_token, project["id"], prod_id, key="O_KEY")

        resp = await test_client.get("/api/approvals", headers=auth(editor_token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["key"] == "E_KEY"

    async def test_viewer_gets_403(self, test_client, viewer_token):
        resp = await test_client.get("/api/approvals", headers=auth(viewer_token))
        assert resp.status_code == 403

    async def test_unauthenticated_gets_401(self, test_client):
        resp = await test_client.get("/api/approvals")
        assert resp.status_code == 401

    async def test_filter_by_status(self, test_client, project, admin_token, editor_token):
        prod_id = _env_id(project, "production")
        ar = await _make_approval(test_client, editor_token, project["id"], prod_id, key="FILT_KEY")

        # Approve it
        await test_client.post(
            f"/api/approvals/{ar['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )

        resp = await test_client.get("/api/approvals", headers=auth(admin_token), params={"status": "pending"})
        assert resp.json()["pagination"]["total"] == 0

        resp = await test_client.get("/api/approvals", headers=auth(admin_token), params={"status": "approved"})
        assert resp.json()["pagination"]["total"] == 1

    async def test_filter_by_project_id(self, test_client, admin_token, editor_token):
        p1 = await _make_project(test_client, admin_token, "Project Alpha")
        p2 = await _make_project(test_client, admin_token, "Project Beta")
        prd1 = _env_id(p1, "production")
        prd2 = _env_id(p2, "production")
        await _make_approval(test_client, editor_token, p1["id"], prd1, key="A_KEY")
        await _make_approval(test_client, editor_token, p2["id"], prd2, key="B_KEY")

        resp = await test_client.get(
            "/api/approvals", headers=auth(admin_token), params={"project_id": p1["id"]}
        )
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["project"]["id"] == p1["id"]

    async def test_pagination(self, test_client, project, admin_token, editor_token):
        prod_id = _env_id(project, "production")
        for i in range(5):
            await _make_approval(test_client, editor_token, project["id"], prod_id, key=f"KEY_{i}")

        resp = await test_client.get(
            "/api/approvals", headers=auth(admin_token), params={"page": 1, "per_page": 2}
        )
        body = resp.json()
        assert body["pagination"]["total"] == 5
        assert body["pagination"]["pages"] == 3
        assert len(body["data"]) == 2

    async def test_response_shape(self, test_client, project, admin_token, pending_approval):
        resp = await test_client.get("/api/approvals", headers=auth(admin_token))
        ar = resp.json()["data"][0]
        for field in ("id", "key", "action", "status", "config_type", "proposed_value",
                      "environment", "project", "requested_by", "created_at"):
            assert field in ar


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/approvals/{id}
# ══════════════════════════════════════════════════════════════════════════════

class TestGetApproval:
    async def test_admin_can_get_any(self, test_client, admin_token, pending_approval):
        resp = await test_client.get(f"/api/approvals/{pending_approval['id']}", headers=auth(admin_token))
        assert resp.status_code == 200
        assert resp.json()["id"] == pending_approval["id"]

    async def test_editor_can_get_own(self, test_client, editor_token, pending_approval):
        resp = await test_client.get(f"/api/approvals/{pending_approval['id']}", headers=auth(editor_token))
        assert resp.status_code == 200

    async def test_editor_cannot_get_other(self, test_client, project, admin_token, editor_token, test_engine):
        prod_id = _env_id(project, "production")
        other = await _make_user(test_engine, "Other Ed", "other2@test.local", "pass1234", "editor")
        from app.security import create_access_token
        other_token = create_access_token(other.id, other.email, other.role)
        ar = await _make_approval(test_client, other_token, project["id"], prod_id, key="OTHER_KEY")

        resp = await test_client.get(f"/api/approvals/{ar['id']}", headers=auth(editor_token))
        assert resp.status_code == 403

    async def test_viewer_gets_403(self, test_client, viewer_token, pending_approval):
        resp = await test_client.get(f"/api/approvals/{pending_approval['id']}", headers=auth(viewer_token))
        assert resp.status_code == 403

    async def test_not_found_gets_404(self, test_client, admin_token):
        resp = await test_client.get("/api/approvals/99999", headers=auth(admin_token))
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/approvals/{id}/approve
# ══════════════════════════════════════════════════════════════════════════════

class TestApproveApproval:
    async def test_approve_create_applies_config(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        prod_id = _env_id(project, "production")
        ar = await _make_approval(
            test_client, editor_token, project["id"], prod_id, key="APPROVED_KEY", value="approved-val"
        )
        resp = await test_client.post(
            f"/api/approvals/{ar['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": "Looks good"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["review_comment"] == "Looks good"

        # Verify config was created in DB
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "APPROVED_KEY", ConfigEntry.environment_id == prod_id)
        )
        config = result.scalar_one_or_none()
        assert config is not None
        assert config.value == "approved-val"

    async def test_approve_create_secret_stays_encrypted(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        prod_id = _env_id(project, "production")
        ar = await _make_approval(
            test_client, editor_token, project["id"], prod_id,
            key="SECRET_APPROVED", value="my-secret", config_type="secret"
        )
        await test_client.post(
            f"/api/approvals/{ar['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "SECRET_APPROVED")
        )
        config = result.scalar_one()
        assert config.value.startswith("gAA")  # still encrypted in DB
        assert config.is_sensitive is True

    async def test_approve_update_applies_new_value(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        prod_id = _env_id(project, "production")
        # Admin creates config directly
        config = await _make_config_direct(
            test_client, admin_token, project["id"], prod_id, key="UPD_KEY", value="original"
        )
        # Editor requests update
        resp = await test_client.put(
            _configs_url(project["id"], prod_id) + f"/{config['id']}",
            headers=auth(editor_token),
            json={"value": "updated"},
        )
        assert resp.status_code == 202
        ar = resp.json()["approval_request"]

        # Admin approves
        await test_client.post(
            f"/api/approvals/{ar['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )

        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.id == config["id"])
        )
        updated = result.scalar_one()
        assert updated.value == "updated"
        assert updated.version == 2

    async def test_approve_delete_removes_config(
        self, test_client, project, admin_token, editor_user, test_engine, db_session
    ):
        from app.models import ApprovalRequest
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        prod_id = _env_id(project, "production")
        config = await _make_config_direct(
            test_client, admin_token, project["id"], prod_id, key="DEL_KEY"
        )

        # Insert a delete ApprovalRequest directly (configs router doesn't expose delete approvals)
        SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
        async with SessionLocal() as s:
            ar_obj = ApprovalRequest(
                config_entry_id=config["id"],
                environment_id=prod_id,
                action="delete",
                key="DEL_KEY",
                proposed_value=None,
                config_type="string",
                current_value="val",
                status="pending",
                requested_by=editor_user.id,
            )
            s.add(ar_obj)
            await s.commit()
            ar_id = ar_obj.id

        # Admin approves
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 200

        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.id == config["id"])
        )
        assert result.scalar_one_or_none() is None

    async def test_approve_already_approved_gets_409(
        self, test_client, project, admin_token, editor_token, pending_approval
    ):
        # Approve once
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        # Try to approve again
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "CONFLICT"

    async def test_approve_rejected_gets_409(
        self, test_client, project, admin_token, editor_token, pending_approval
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 409

    async def test_editor_cannot_approve(self, test_client, editor_token, pending_approval):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(editor_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_approve(self, test_client, viewer_token, pending_approval):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(viewer_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 403

    async def test_not_found_gets_404(self, test_client, admin_token):
        resp = await test_client.post(
            "/api/approvals/99999/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 404

    async def test_creates_audit_logs(
        self, test_client, project, admin_token, editor_token, db_session, pending_approval
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": "ok"},
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "approval_approved")
        )
        assert result.scalar_one_or_none() is not None

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "config_created")
        )
        assert result.scalar_one_or_none() is not None

    async def test_approve_sets_reviewed_fields(
        self, test_client, admin_token, admin_user, pending_approval
    ):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": "approved!"},
        )
        data = resp.json()
        assert data["reviewed_by"]["id"] == admin_user.id
        assert data["reviewed_at"] is not None
        assert data["review_comment"] == "approved!"


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/approvals/{id}/reject
# ══════════════════════════════════════════════════════════════════════════════

class TestRejectApproval:
    async def test_reject_does_not_create_config(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        prod_id = _env_id(project, "production")
        ar = await _make_approval(
            test_client, editor_token, project["id"], prod_id, key="REJECTED_KEY"
        )
        resp = await test_client.post(
            f"/api/approvals/{ar['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": "Value incorrect"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # Config should NOT exist
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "REJECTED_KEY")
        )
        assert result.scalar_one_or_none() is None

    async def test_reject_sets_reviewed_fields(
        self, test_client, admin_token, admin_user, pending_approval
    ):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": "No way"},
        )
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["reviewed_by"]["id"] == admin_user.id
        assert data["review_comment"] == "No way"
        assert data["reviewed_at"] is not None

    async def test_reject_already_rejected_gets_409(
        self, test_client, admin_token, pending_approval
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 409

    async def test_reject_approved_gets_409(
        self, test_client, admin_token, pending_approval
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 409

    async def test_editor_cannot_reject(self, test_client, editor_token, pending_approval):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(editor_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_reject(self, test_client, viewer_token, pending_approval):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(viewer_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 403

    async def test_not_found_gets_404(self, test_client, admin_token):
        resp = await test_client.post(
            "/api/approvals/99999/reject",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 404

    async def test_creates_audit_log(
        self, test_client, admin_token, pending_approval, db_session
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "approval_rejected")
        )
        assert result.scalar_one_or_none() is not None


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/approvals/{id}/cancel
# ══════════════════════════════════════════════════════════════════════════════

class TestCancelApproval:
    async def test_editor_cancels_own(self, test_client, editor_token, pending_approval):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/cancel",
            headers=auth(editor_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_admin_can_cancel_any(self, test_client, admin_token, pending_approval):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/cancel",
            headers=auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    async def test_editor_cannot_cancel_other(
        self, test_client, project, editor_token, test_engine
    ):
        prod_id = _env_id(project, "production")
        other = await _make_user(test_engine, "Other Ed3", "other3@test.local", "pass1234", "editor")
        from app.security import create_access_token
        other_token = create_access_token(other.id, other.email, other.role)
        ar = await _make_approval(test_client, other_token, project["id"], prod_id, key="CANT_CANCEL")

        resp = await test_client.post(
            f"/api/approvals/{ar['id']}/cancel",
            headers=auth(editor_token),
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_cancel(self, test_client, viewer_token, pending_approval):
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/cancel",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_cancel_approved_gets_409(
        self, test_client, admin_token, editor_token, pending_approval
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/cancel",
            headers=auth(editor_token),
        )
        assert resp.status_code == 409

    async def test_cancel_already_cancelled_gets_409(
        self, test_client, editor_token, pending_approval
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/cancel",
            headers=auth(editor_token),
        )
        resp = await test_client.post(
            f"/api/approvals/{pending_approval['id']}/cancel",
            headers=auth(editor_token),
        )
        assert resp.status_code == 409

    async def test_not_found_gets_404(self, test_client, editor_token):
        resp = await test_client.post(
            "/api/approvals/99999/cancel",
            headers=auth(editor_token),
        )
        assert resp.status_code == 404

    async def test_creates_audit_log(
        self, test_client, editor_token, pending_approval, db_session
    ):
        await test_client.post(
            f"/api/approvals/{pending_approval['id']}/cancel",
            headers=auth(editor_token),
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "approval_cancelled")
        )
        assert result.scalar_one_or_none() is not None


# ══════════════════════════════════════════════════════════════════════════════
# Full flow: create → approve → verify / create → reject → verify
# ══════════════════════════════════════════════════════════════════════════════

class TestFullApprovalFlow:
    async def test_full_create_approve_verify(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        """Editor requests create → admin approves → config appears in production."""
        prod_id = _env_id(project, "production")

        # 1. Editor tries to create in production → 202
        ar = await _make_approval(
            test_client, editor_token, project["id"], prod_id,
            key="FULL_FLOW_KEY", value="production-value"
        )
        assert ar["status"] == "pending"
        assert ar["action"] == "create"

        # 2. Config does NOT exist yet
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "FULL_FLOW_KEY")
        )
        assert result.scalar_one_or_none() is None

        # 3. Admin approves
        resp = await test_client.post(
            f"/api/approvals/{ar['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": "All good"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # 4. Config NOW exists in production
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "FULL_FLOW_KEY")
        )
        config = result.scalar_one_or_none()
        assert config is not None
        assert config.value == "production-value"
        assert config.environment_id == prod_id

        # 5. Config visible via GET configs endpoint
        list_resp = await test_client.get(
            f"/api/projects/{project['id']}/environments/{prod_id}/configs",
            headers=auth(admin_token),
        )
        keys = [c["key"] for c in list_resp.json()]
        assert "FULL_FLOW_KEY" in keys

    async def test_full_create_reject_no_config(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        """Editor requests create → admin rejects → config does NOT appear."""
        prod_id = _env_id(project, "production")

        ar = await _make_approval(
            test_client, editor_token, project["id"], prod_id,
            key="REJECTED_FLOW_KEY", value="should-not-exist"
        )
        await test_client.post(
            f"/api/approvals/{ar['id']}/reject",
            headers=auth(admin_token),
            json={"review_comment": "Not approved"},
        )

        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "REJECTED_FLOW_KEY")
        )
        assert result.scalar_one_or_none() is None

    async def test_full_update_approve_flow(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        """Admin creates config in production → editor requests update → admin approves → value changes."""
        prod_id = _env_id(project, "production")

        # Admin creates directly
        config = await _make_config_direct(
            test_client, admin_token, project["id"], prod_id, key="UPDATE_FLOW", value="old-value"
        )

        # Editor requests update → 202
        resp = await test_client.put(
            f"/api/projects/{project['id']}/environments/{prod_id}/configs/{config['id']}",
            headers=auth(editor_token),
            json={"value": "new-value"},
        )
        assert resp.status_code == 202
        ar = resp.json()["approval_request"]
        assert ar["proposed_value"] == "new-value"
        assert ar["current_value"] == "old-value"

        # Admin approves
        resp = await test_client.post(
            f"/api/approvals/{ar['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 200

        # Verify value changed in DB
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.id == config["id"])
        )
        updated = result.scalar_one()
        assert updated.value == "new-value"
        assert updated.version == 2

    async def test_full_toggle_approve_flow(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        """Admin creates feature_flag in production → editor toggles → admin approves → value flips."""
        prod_id = _env_id(project, "production")
        config = await _make_config_direct(
            test_client, admin_token, project["id"], prod_id,
            key="FF_TOGGLE_FLOW", value="false", config_type="feature_flag"
        )

        # Editor toggles → 202
        resp = await test_client.put(
            f"/api/projects/{project['id']}/environments/{prod_id}/configs/{config['id']}/toggle",
            headers=auth(editor_token),
        )
        assert resp.status_code == 202
        ar = resp.json()["approval_request"]
        assert ar["proposed_value"] == "true"
        assert ar["current_value"] == "false"

        # Admin approves
        await test_client.post(
            f"/api/approvals/{ar['id']}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )

        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.id == config["id"])
        )
        ff = result.scalar_one()
        assert ff.value == "true"
        assert ff.version == 2
