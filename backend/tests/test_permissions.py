"""
Exhaustive permission matrix tests for Config Vault.

Covers:
  1. Unit tests for has_permission() — every (role, resource, action) combination
  2. HTTP integration tests — every endpoint × role combination
     - Users endpoints (admin-only)
     - Projects endpoints (admin/editor/viewer)
     - Configs dev (admin/editor/viewer)
     - Configs production (admin=direct, editor=approval, viewer=403)
     - Approvals (admin/editor/viewer per action)
     - Audit (admin=global, editor/viewer=project-level)
"""
import pytest

from app.permissions import PERMISSIONS, has_permission


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: has_permission() — every combination in the matrix
# ══════════════════════════════════════════════════════════════════════════════

class TestHasPermissionAdmin:
    # users
    def test_admin_users_list(self):       assert has_permission("admin", "users", "list") is True
    def test_admin_users_create(self):     assert has_permission("admin", "users", "create") is True
    def test_admin_users_edit_role(self):  assert has_permission("admin", "users", "edit_role") is True
    def test_admin_users_deactivate(self): assert has_permission("admin", "users", "deactivate") is True

    # projects
    def test_admin_projects_list(self):    assert has_permission("admin", "projects", "list") is True
    def test_admin_projects_create(self):  assert has_permission("admin", "projects", "create") is True
    def test_admin_projects_edit(self):    assert has_permission("admin", "projects", "edit") is True
    def test_admin_projects_delete(self):  assert has_permission("admin", "projects", "delete") is True
    def test_admin_projects_view(self):    assert has_permission("admin", "projects", "view") is True

    # configs
    def test_admin_configs_list(self):         assert has_permission("admin", "configs", "list") is True
    def test_admin_configs_view(self):         assert has_permission("admin", "configs", "view") is True
    def test_admin_configs_view_secret(self):  assert has_permission("admin", "configs", "view_secret") is True
    def test_admin_configs_create(self):       assert has_permission("admin", "configs", "create") is True
    def test_admin_configs_edit(self):         assert has_permission("admin", "configs", "edit") is True
    def test_admin_configs_delete(self):       assert has_permission("admin", "configs", "delete") is True

    # configs_production
    def test_admin_configs_prod_create_direct(self): assert has_permission("admin", "configs_production", "create_direct") is True
    def test_admin_configs_prod_edit_direct(self):   assert has_permission("admin", "configs_production", "edit_direct") is True
    def test_admin_configs_prod_delete(self):         assert has_permission("admin", "configs_production", "delete") is True

    # approvals
    def test_admin_approvals_list_all(self): assert has_permission("admin", "approvals", "list_all") is True
    def test_admin_approvals_approve(self):  assert has_permission("admin", "approvals", "approve") is True
    def test_admin_approvals_reject(self):   assert has_permission("admin", "approvals", "reject") is True

    # audit
    def test_admin_audit_view_all(self): assert has_permission("admin", "audit", "view_all") is True
    def test_admin_audit_export(self):   assert has_permission("admin", "audit", "export") is True

    # admin does NOT have editor-only permissions
    def test_admin_not_edit_own(self):              assert has_permission("admin", "projects", "edit_own") is False
    def test_admin_not_create_with_approval(self):  assert has_permission("admin", "configs_production", "create_with_approval") is False
    def test_admin_not_list_own_approvals(self):    assert has_permission("admin", "approvals", "list_own") is False


class TestHasPermissionEditor:
    # users — none
    def test_editor_users_list(self):       assert has_permission("editor", "users", "list") is False
    def test_editor_users_create(self):     assert has_permission("editor", "users", "create") is False
    def test_editor_users_edit_role(self):  assert has_permission("editor", "users", "edit_role") is False
    def test_editor_users_deactivate(self): assert has_permission("editor", "users", "deactivate") is False

    # projects
    def test_editor_projects_list(self):   assert has_permission("editor", "projects", "list") is True
    def test_editor_projects_create(self): assert has_permission("editor", "projects", "create") is True
    def test_editor_projects_edit_own(self): assert has_permission("editor", "projects", "edit_own") is True
    def test_editor_projects_view(self):   assert has_permission("editor", "projects", "view") is True
    def test_editor_projects_no_edit(self):   assert has_permission("editor", "projects", "edit") is False
    def test_editor_projects_no_delete(self): assert has_permission("editor", "projects", "delete") is False

    # configs
    def test_editor_configs_list(self):         assert has_permission("editor", "configs", "list") is True
    def test_editor_configs_view(self):         assert has_permission("editor", "configs", "view") is True
    def test_editor_configs_view_secret(self):  assert has_permission("editor", "configs", "view_secret") is True
    def test_editor_configs_create(self):       assert has_permission("editor", "configs", "create") is True
    def test_editor_configs_edit(self):         assert has_permission("editor", "configs", "edit") is True
    def test_editor_configs_delete(self):       assert has_permission("editor", "configs", "delete") is True

    # configs_production
    def test_editor_configs_prod_create_with_approval(self): assert has_permission("editor", "configs_production", "create_with_approval") is True
    def test_editor_configs_prod_edit_with_approval(self):   assert has_permission("editor", "configs_production", "edit_with_approval") is True
    def test_editor_configs_prod_no_create_direct(self):     assert has_permission("editor", "configs_production", "create_direct") is False
    def test_editor_configs_prod_no_delete(self):             assert has_permission("editor", "configs_production", "delete") is False

    # approvals
    def test_editor_approvals_list_own(self):   assert has_permission("editor", "approvals", "list_own") is True
    def test_editor_approvals_create(self):     assert has_permission("editor", "approvals", "create") is True
    def test_editor_approvals_cancel_own(self): assert has_permission("editor", "approvals", "cancel_own") is True
    def test_editor_approvals_no_list_all(self): assert has_permission("editor", "approvals", "list_all") is False
    def test_editor_approvals_no_approve(self):  assert has_permission("editor", "approvals", "approve") is False
    def test_editor_approvals_no_reject(self):   assert has_permission("editor", "approvals", "reject") is False

    # audit
    def test_editor_audit_view_project(self):  assert has_permission("editor", "audit", "view_project") is True
    def test_editor_audit_no_view_all(self):   assert has_permission("editor", "audit", "view_all") is False
    def test_editor_audit_no_export(self):     assert has_permission("editor", "audit", "export") is False


class TestHasPermissionViewer:
    # users — none
    def test_viewer_users_list(self):   assert has_permission("viewer", "users", "list") is False
    def test_viewer_users_create(self): assert has_permission("viewer", "users", "create") is False

    # projects
    def test_viewer_projects_list(self):   assert has_permission("viewer", "projects", "list") is True
    def test_viewer_projects_view(self):   assert has_permission("viewer", "projects", "view") is True
    def test_viewer_projects_no_create(self): assert has_permission("viewer", "projects", "create") is False
    def test_viewer_projects_no_edit(self):   assert has_permission("viewer", "projects", "edit") is False
    def test_viewer_projects_no_delete(self): assert has_permission("viewer", "projects", "delete") is False

    # configs
    def test_viewer_configs_list(self):        assert has_permission("viewer", "configs", "list") is True
    def test_viewer_configs_view(self):        assert has_permission("viewer", "configs", "view") is True
    def test_viewer_configs_no_view_secret(self): assert has_permission("viewer", "configs", "view_secret") is False
    def test_viewer_configs_no_create(self):   assert has_permission("viewer", "configs", "create") is False
    def test_viewer_configs_no_edit(self):     assert has_permission("viewer", "configs", "edit") is False
    def test_viewer_configs_no_delete(self):   assert has_permission("viewer", "configs", "delete") is False

    # configs_production — all forbidden
    def test_viewer_configs_prod_no_create(self): assert has_permission("viewer", "configs_production", "create_with_approval") is False
    def test_viewer_configs_prod_no_edit(self):   assert has_permission("viewer", "configs_production", "edit_with_approval") is False
    def test_viewer_configs_prod_no_delete(self): assert has_permission("viewer", "configs_production", "delete") is False

    # approvals — all forbidden
    def test_viewer_approvals_no_list_own(self):   assert has_permission("viewer", "approvals", "list_own") is False
    def test_viewer_approvals_no_list_all(self):   assert has_permission("viewer", "approvals", "list_all") is False
    def test_viewer_approvals_no_approve(self):    assert has_permission("viewer", "approvals", "approve") is False
    def test_viewer_approvals_no_cancel(self):     assert has_permission("viewer", "approvals", "cancel_own") is False

    # audit
    def test_viewer_audit_view_project(self):  assert has_permission("viewer", "audit", "view_project") is True
    def test_viewer_audit_no_view_all(self):   assert has_permission("viewer", "audit", "view_all") is False
    def test_viewer_audit_no_export(self):     assert has_permission("viewer", "audit", "export") is False


class TestHasPermissionEdgeCases:
    def test_unknown_role_returns_false(self):
        assert has_permission("superuser", "configs", "create") is False

    def test_unknown_resource_returns_false(self):
        assert has_permission("admin", "unknown_resource", "create") is False

    def test_unknown_action_returns_false(self):
        assert has_permission("admin", "configs", "unknown_action") is False

    def test_empty_role_returns_false(self):
        assert has_permission("", "configs", "create") is False

    def test_matrix_has_three_roles(self):
        assert set(PERMISSIONS.keys()) == {"admin", "editor", "viewer"}

    def test_matrix_has_all_resources(self):
        expected = {"users", "projects", "configs", "configs_production", "approvals", "audit"}
        for role_perms in PERMISSIONS.values():
            assert set(role_perms.keys()) == expected


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

async def _make_project(client, token, name="Perm Test Project") -> dict:
    resp = await client.post("/api/projects", headers=auth(token), json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _dev_id(project):
    return next(e["id"] for e in project["environments"] if e["name"] == "development")


def _prod_id(project):
    return next(e["id"] for e in project["environments"] if e["name"] == "production")


async def _make_config(client, token, project_id, env_id, key="PERM_KEY", config_type="string") -> dict:
    resp = await client.post(
        f"/api/projects/{project_id}/environments/{env_id}/configs",
        headers=auth(token),
        json={"key": key, "value": "test-value", "config_type": config_type},
    )
    assert resp.status_code in (201, 202)
    return resp.json()


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: Users endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TestUsersPermissions:
    """GET /api/users and POST /api/users are admin-only."""

    async def test_admin_can_list_users(self, test_client, admin_token):
        resp = await test_client.get("/api/users", headers=auth(admin_token))
        assert resp.status_code == 200

    async def test_editor_cannot_list_users(self, test_client, editor_token):
        resp = await test_client.get("/api/users", headers=auth(editor_token))
        assert resp.status_code == 403

    async def test_viewer_cannot_list_users(self, test_client, viewer_token):
        resp = await test_client.get("/api/users", headers=auth(viewer_token))
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_list_users(self, test_client):
        resp = await test_client.get("/api/users")
        assert resp.status_code == 401

    async def test_admin_can_create_user(self, test_client, admin_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={"name": "New User", "email": "newuser_perm@test.local",
                  "password": "pass1234", "role": "viewer"},
        )
        assert resp.status_code == 201

    async def test_editor_cannot_create_user(self, test_client, editor_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(editor_token),
            json={"name": "Hacker", "email": "hacker@test.local",
                  "password": "pass1234", "role": "admin"},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_create_user(self, test_client, viewer_token):
        resp = await test_client.post(
            "/api/users",
            headers=auth(viewer_token),
            json={"name": "Sneaky", "email": "sneaky@test.local",
                  "password": "pass1234", "role": "viewer"},
        )
        assert resp.status_code == 403

    async def test_admin_can_edit_user_role(self, test_client, admin_token, editor_user):
        resp = await test_client.put(
            f"/api/users/{editor_user.id}",
            headers=auth(admin_token),
            json={"role": "viewer"},
        )
        assert resp.status_code == 200

    async def test_editor_cannot_edit_role(self, test_client, editor_token, viewer_user):
        resp = await test_client.put(
            f"/api/users/{viewer_user.id}",
            headers=auth(editor_token),
            json={"role": "admin"},
        )
        assert resp.status_code == 403

    async def test_admin_can_deactivate_user(self, test_client, admin_token, viewer_user):
        resp = await test_client.put(
            f"/api/users/{viewer_user.id}",
            headers=auth(admin_token),
            json={"is_active": False},
        )
        assert resp.status_code == 200

    async def test_editor_cannot_deactivate_user(self, test_client, editor_token, viewer_user):
        resp = await test_client.put(
            f"/api/users/{viewer_user.id}",
            headers=auth(editor_token),
            json={"is_active": False},
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: Projects endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TestProjectsPermissions:
    async def test_admin_can_list_projects(self, test_client, admin_token):
        resp = await test_client.get("/api/projects", headers=auth(admin_token))
        assert resp.status_code == 200

    async def test_editor_can_list_projects(self, test_client, editor_token):
        resp = await test_client.get("/api/projects", headers=auth(editor_token))
        assert resp.status_code == 200

    async def test_viewer_can_list_projects(self, test_client, viewer_token):
        resp = await test_client.get("/api/projects", headers=auth(viewer_token))
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_list_projects(self, test_client):
        resp = await test_client.get("/api/projects")
        assert resp.status_code == 401

    async def test_admin_can_create_project(self, test_client, admin_token):
        resp = await test_client.post(
            "/api/projects", headers=auth(admin_token), json={"name": "Admin Proj"}
        )
        assert resp.status_code == 201

    async def test_editor_can_create_project(self, test_client, editor_token):
        resp = await test_client.post(
            "/api/projects", headers=auth(editor_token), json={"name": "Editor Proj"}
        )
        assert resp.status_code == 201

    async def test_viewer_cannot_create_project(self, test_client, viewer_token):
        resp = await test_client.post(
            "/api/projects", headers=auth(viewer_token), json={"name": "Viewer Proj"}
        )
        assert resp.status_code == 403

    async def test_admin_can_edit_any_project(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Edit Target")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(admin_token),
            json={"name": "Edited"},
        )
        assert resp.status_code == 200

    async def test_editor_can_edit_own_project(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Editor Own")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(editor_token),
            json={"name": "Editor Edited"},
        )
        assert resp.status_code == 200

    async def test_editor_cannot_edit_other_project(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, admin_token, "Admin Owns This")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(editor_token),
            json={"name": "Hijacked"},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_edit_project(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Viewer Target")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}",
            headers=auth(viewer_token),
            json={"name": "Viewer Edit"},
        )
        assert resp.status_code == 403

    async def test_admin_can_delete_project(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "To Delete")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}", headers=auth(admin_token)
        )
        assert resp.status_code == 204

    async def test_editor_cannot_delete_project(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Editor Del")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}", headers=auth(editor_token)
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_delete_project(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Viewer Del")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}", headers=auth(viewer_token)
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: Configs — development environment
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigsDevPermissions:
    async def test_admin_can_list_dev_configs(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Dev List Admin")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{_dev_id(proj)}/configs",
            headers=auth(admin_token),
        )
        assert resp.status_code == 200

    async def test_editor_can_list_dev_configs(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, admin_token, "Dev List Editor")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{_dev_id(proj)}/configs",
            headers=auth(editor_token),
        )
        assert resp.status_code == 200

    async def test_viewer_can_list_dev_configs(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Dev List Viewer")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{_dev_id(proj)}/configs",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_list_dev_configs(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Dev List Unauth")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{_dev_id(proj)}/configs",
        )
        assert resp.status_code == 401

    async def test_admin_can_create_dev_config(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Dev Create Admin")
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{_dev_id(proj)}/configs",
            headers=auth(admin_token),
            json={"key": "ADMIN_KEY", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 201

    async def test_editor_can_create_dev_config(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Dev Create Editor")
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{_dev_id(proj)}/configs",
            headers=auth(editor_token),
            json={"key": "EDITOR_KEY", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 201

    async def test_viewer_cannot_create_dev_config(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Dev Create Viewer")
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{_dev_id(proj)}/configs",
            headers=auth(viewer_token),
            json={"key": "VIEWER_KEY", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 403

    async def test_admin_can_update_dev_config(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Dev Upd Admin")
        dev = _dev_id(proj)
        cfg = await _make_config(test_client, admin_token, proj["id"], dev, "UPD_ADMIN")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg['id']}",
            headers=auth(admin_token),
            json={"value": "new"},
        )
        assert resp.status_code == 200

    async def test_editor_can_update_dev_config(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Dev Upd Editor")
        dev = _dev_id(proj)
        cfg = await _make_config(test_client, editor_token, proj["id"], dev, "UPD_EDITOR")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg['id']}",
            headers=auth(editor_token),
            json={"value": "new"},
        )
        assert resp.status_code == 200

    async def test_viewer_cannot_update_dev_config(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Dev Upd Viewer")
        dev = _dev_id(proj)
        cfg = await _make_config(test_client, admin_token, proj["id"], dev, "UPD_VIEWER")
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg['id']}",
            headers=auth(viewer_token),
            json={"value": "new"},
        )
        assert resp.status_code == 403

    async def test_admin_can_delete_dev_config(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Dev Del Admin")
        dev = _dev_id(proj)
        cfg = await _make_config(test_client, admin_token, proj["id"], dev, "DEL_ADMIN")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg['id']}",
            headers=auth(admin_token),
        )
        assert resp.status_code == 204

    async def test_editor_can_delete_dev_config(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Dev Del Editor")
        dev = _dev_id(proj)
        cfg = await _make_config(test_client, editor_token, proj["id"], dev, "DEL_EDITOR")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg['id']}",
            headers=auth(editor_token),
        )
        assert resp.status_code == 204

    async def test_viewer_cannot_delete_dev_config(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Dev Del Viewer")
        dev = _dev_id(proj)
        cfg = await _make_config(test_client, admin_token, proj["id"], dev, "DEL_VIEWER")
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg['id']}",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_viewer_sees_masked_secret(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Dev Secret Viewer")
        dev = _dev_id(proj)
        await _make_config(test_client, admin_token, proj["id"], dev, "SEC_KEY", config_type="secret")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(viewer_token),
        )
        item = next(c for c in resp.json() if c["key"] == "SEC_KEY")
        assert item["value"] == "********"

    async def test_admin_sees_decrypted_secret(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Dev Secret Admin")
        dev = _dev_id(proj)
        await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "SEC_PLAIN", "value": "my-secret", "config_type": "secret"},
        )
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        item = next(c for c in resp.json() if c["key"] == "SEC_PLAIN")
        assert item["value"] == "my-secret"

    async def test_viewer_cannot_reveal_secret(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Dev Reveal Viewer")
        dev = _dev_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "REVEAL_SEC", "value": "hidden", "config_type": "secret"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg_id}/reveal",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_editor_can_reveal_secret(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, admin_token, "Dev Reveal Editor")
        dev = _dev_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "REVEAL_ED", "value": "editorvalue", "config_type": "secret"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg_id}/reveal",
            headers=auth(editor_token),
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "editorvalue"


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: Configs — production environment
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigsProductionPermissions:
    """Production config writes go through approval for editors."""

    async def test_admin_creates_prod_config_directly(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Prod Create Admin")
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{_prod_id(proj)}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_ADMIN", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 201

    async def test_editor_creates_prod_config_as_approval(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Prod Create Editor")
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{_prod_id(proj)}/configs",
            headers=auth(editor_token),
            json={"key": "PROD_EDITOR", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 202
        assert "approval_request" in resp.json()

    async def test_viewer_cannot_create_prod_config(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Prod Create Viewer")
        resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{_prod_id(proj)}/configs",
            headers=auth(viewer_token),
            json={"key": "PROD_VIEWER", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 403

    async def test_admin_updates_prod_config_directly(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Prod Upd Admin")
        prod = _prod_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_UPD_ADMIN", "value": "old", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}",
            headers=auth(admin_token),
            json={"value": "new"},
        )
        assert resp.status_code == 200

    async def test_editor_updates_prod_config_via_approval(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, admin_token, "Prod Upd Editor")
        prod = _prod_id(proj)
        # Admin creates config first
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_UPD_ED", "value": "old", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]
        # Editor update → 202
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}",
            headers=auth(editor_token),
            json={"value": "new"},
        )
        assert resp.status_code == 202

    async def test_viewer_cannot_update_prod_config(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Prod Upd Viewer")
        prod = _prod_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_UPD_VIEW", "value": "v", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}",
            headers=auth(viewer_token),
            json={"value": "new"},
        )
        assert resp.status_code == 403

    async def test_admin_can_delete_prod_config(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Prod Del Admin")
        prod = _prod_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_DEL_ADMIN", "value": "v", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}",
            headers=auth(admin_token),
        )
        assert resp.status_code == 204

    async def test_editor_cannot_delete_prod_config(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, admin_token, "Prod Del Editor")
        prod = _prod_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_DEL_ED", "value": "v", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}",
            headers=auth(editor_token),
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_delete_prod_config(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Prod Del Viewer")
        prod = _prod_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_DEL_VIEW", "value": "v", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.delete(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_editor_toggle_prod_feature_flag_via_approval(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, admin_token, "Prod Toggle Editor")
        prod = _prod_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_FF", "value": "true", "config_type": "feature_flag"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}/toggle",
            headers=auth(editor_token),
        )
        assert resp.status_code == 202

    async def test_viewer_cannot_toggle_prod_feature_flag(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Prod Toggle Viewer")
        prod = _prod_id(proj)
        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
            json={"key": "PROD_FF_V", "value": "true", "config_type": "feature_flag"},
        )
        cfg_id = cfg_resp.json()["id"]
        resp = await test_client.put(
            f"/api/projects/{proj['id']}/environments/{prod}/configs/{cfg_id}/toggle",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: Approvals
# ══════════════════════════════════════════════════════════════════════════════

class TestApprovalsPermissions:
    async def test_admin_can_list_all_approvals(self, test_client, admin_token):
        resp = await test_client.get("/api/approvals", headers=auth(admin_token))
        assert resp.status_code == 200

    async def test_editor_can_list_own_approvals(self, test_client, editor_token):
        resp = await test_client.get("/api/approvals", headers=auth(editor_token))
        assert resp.status_code == 200

    async def test_viewer_cannot_list_approvals(self, test_client, viewer_token):
        resp = await test_client.get("/api/approvals", headers=auth(viewer_token))
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_list_approvals(self, test_client):
        resp = await test_client.get("/api/approvals")
        assert resp.status_code == 401

    async def test_admin_can_approve(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, editor_token, "Approve Perm Test")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "TO_APPROVE", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 200

    async def test_editor_cannot_approve(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, editor_token, "Editor Approve Block")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "ED_CANT_APPROVE", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/approve",
            headers=auth(editor_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_approve(self, test_client, editor_token, viewer_token):
        proj = await _make_project(test_client, editor_token, "Viewer Approve Block")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "VIEW_CANT_APPROVE", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/approve",
            headers=auth(viewer_token),
            json={"review_comment": None},
        )
        assert resp.status_code == 403

    async def test_admin_can_reject(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, editor_token, "Reject Perm Test")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "TO_REJECT", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/reject",
            headers=auth(admin_token),
            json={"review_comment": "Denied"},
        )
        assert resp.status_code == 200

    async def test_editor_cannot_reject(self, test_client, admin_token, editor_token):
        proj = await _make_project(test_client, editor_token, "Editor Reject Block")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "ED_REJECT_BLOCK", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/reject",
            headers=auth(editor_token),
            json={"review_comment": "Nope"},
        )
        assert resp.status_code == 403

    async def test_editor_can_cancel_own_approval(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Cancel Own Test")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "TO_CANCEL", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/cancel",
            headers=auth(editor_token),
        )
        assert resp.status_code == 200

    async def test_editor_cannot_cancel_other_editors_approval(
        self, test_client, admin_token, editor_token, viewer_token
    ):
        # Create a second editor
        await test_client.post(
            "/api/users",
            headers=auth(admin_token),
            json={"name": "Editor 2", "email": "editor2_perm@test.local",
                  "password": "pass1234", "role": "editor"},
        )
        from app.security import create_access_token
        # Get editor2 from response
        users_resp = await test_client.get("/api/users", headers=auth(admin_token))
        editor2 = next(u for u in users_resp.json()["data"] if u["email"] == "editor2_perm@test.local")
        editor2_token = create_access_token(editor2["id"], editor2["email"], editor2["role"])

        proj = await _make_project(test_client, editor_token, "Other Editor Cancel")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "OTHER_CANCEL", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/cancel",
            headers=auth(editor2_token),
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_cancel_approval(self, test_client, editor_token, viewer_token):
        proj = await _make_project(test_client, editor_token, "Viewer Cancel Block")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "VIEW_CANCEL", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.post(
            f"/api/approvals/{ar_id}/cancel",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_editor_can_get_own_approval(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Get Own AR")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "GET_OWN_AR", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.get(f"/api/approvals/{ar_id}", headers=auth(editor_token))
        assert resp.status_code == 200

    async def test_viewer_cannot_get_approval(self, test_client, editor_token, viewer_token):
        proj = await _make_project(test_client, editor_token, "Get AR Viewer")
        prod = _prod_id(proj)
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "GET_AR_VIEW", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]
        resp = await test_client.get(f"/api/approvals/{ar_id}", headers=auth(viewer_token))
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# HTTP: Audit endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditPermissions:
    async def test_admin_can_access_global_audit(self, test_client, admin_token):
        resp = await test_client.get("/api/audit", headers=auth(admin_token))
        assert resp.status_code == 200

    async def test_editor_cannot_access_global_audit(self, test_client, editor_token):
        resp = await test_client.get("/api/audit", headers=auth(editor_token))
        assert resp.status_code == 403

    async def test_viewer_cannot_access_global_audit(self, test_client, viewer_token):
        resp = await test_client.get("/api/audit", headers=auth(viewer_token))
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_access_global_audit(self, test_client):
        resp = await test_client.get("/api/audit")
        assert resp.status_code == 401

    async def test_admin_can_export_audit(self, test_client, admin_token):
        resp = await test_client.get("/api/audit/export", headers=auth(admin_token))
        assert resp.status_code == 200

    async def test_editor_cannot_export_audit(self, test_client, editor_token):
        resp = await test_client.get("/api/audit/export", headers=auth(editor_token))
        assert resp.status_code == 403

    async def test_viewer_cannot_export_audit(self, test_client, viewer_token):
        resp = await test_client.get("/api/audit/export", headers=auth(viewer_token))
        assert resp.status_code == 403

    async def test_admin_can_access_project_audit(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Audit Proj Admin")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/audit", headers=auth(admin_token)
        )
        assert resp.status_code == 200

    async def test_editor_owner_can_access_project_audit(self, test_client, editor_token):
        proj = await _make_project(test_client, editor_token, "Audit Proj Editor Own")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/audit", headers=auth(editor_token)
        )
        assert resp.status_code == 200

    async def test_editor_non_owner_cannot_access_project_audit(
        self, test_client, admin_token, editor_token
    ):
        proj = await _make_project(test_client, admin_token, "Audit Proj Admin Owned")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/audit", headers=auth(editor_token)
        )
        assert resp.status_code == 403

    async def test_viewer_can_access_project_audit(self, test_client, admin_token, viewer_token):
        proj = await _make_project(test_client, admin_token, "Audit Proj Viewer")
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/audit", headers=auth(viewer_token)
        )
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_access_project_audit(self, test_client, admin_token):
        proj = await _make_project(test_client, admin_token, "Audit Proj Unauth")
        resp = await test_client.get(f"/api/projects/{proj['id']}/audit")
        assert resp.status_code == 401
