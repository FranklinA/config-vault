"""
Tests for /api/projects/{project_id}/environments/{env_id}/configs/* (Fase 3).

Coverage:
  - GET    list_configs        — all roles, secret masking, filters
  - POST   create_config       — all types, validation, approval (editor+production)
  - PUT    update_config       — version increment, approval path
  - DELETE delete_config       — role guards (editor blocked on production)
  - POST   reveal              — secret decryption, audit, non-secret 400
  - PUT    toggle              — feature_flag toggle, approval path, wrong type 400
"""
import pytest
from sqlalchemy import select

from app.models import AuditLog, ConfigEntry
from tests.conftest import _make_user


# ─── Helpers ──────────────────────────────────────────────────────────────────

def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_project(client, token: str, name: str = "Test Project") -> dict:
    resp = await client.post(
        "/api/projects",
        headers=auth(token),
        json={"name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _env_id(project: dict, env_name: str) -> int:
    for e in project["environments"]:
        if e["name"] == env_name:
            return e["id"]
    raise ValueError(f"Environment {env_name!r} not found")


def _configs_url(project_id: int, env_id: int) -> str:
    return f"/api/projects/{project_id}/environments/{env_id}/configs"


async def _make_config(
    client,
    token: str,
    project_id: int,
    env_id: int,
    *,
    key: str = "MY_KEY",
    value: str = "hello",
    config_type: str = "string",
    description: str = "",
) -> dict:
    resp = await client.post(
        _configs_url(project_id, env_id),
        headers=auth(token),
        json={
            "key": key,
            "value": value,
            "config_type": config_type,
            "description": description,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def project(test_client, admin_token):
    """Admin-owned project with dev/staging/production environments."""
    return await _make_project(test_client, admin_token, "Config Test Project")


# ══════════════════════════════════════════════════════════════════════════════
# GET /configs
# ══════════════════════════════════════════════════════════════════════════════

class TestListConfigs:
    async def test_returns_empty_list_initially(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.get(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_all_roles_can_list(self, test_client, project, admin_token, editor_token, viewer_token):
        dev_id = _env_id(project, "development")
        url = _configs_url(project["id"], dev_id)
        for token in (admin_token, editor_token, viewer_token):
            resp = await test_client.get(url, headers=auth(token))
            assert resp.status_code == 200

    async def test_unauthenticated_gets_401(self, test_client, project):
        dev_id = _env_id(project, "development")
        resp = await test_client.get(_configs_url(project["id"], dev_id))
        assert resp.status_code == 401

    async def test_wrong_project_env_gets_404(self, test_client, project, admin_token):
        bad_project_id = project["id"] + 999
        dev_id = _env_id(project, "development")
        resp = await test_client.get(
            _configs_url(bad_project_id, dev_id),
            headers=auth(admin_token),
        )
        assert resp.status_code == 404

    async def test_viewer_sees_masked_secret(self, test_client, project, admin_token, viewer_token):
        dev_id = _env_id(project, "development")
        await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="DB_PASSWORD", value="s3cr3t", config_type="secret",
        )
        resp = await test_client.get(
            _configs_url(project["id"], dev_id),
            headers=auth(viewer_token),
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["value"] == "********"
        assert items[0]["is_sensitive"] is True

    async def test_admin_sees_decrypted_secret(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="DB_PASSWORD", value="s3cr3t", config_type="secret",
        )
        resp = await test_client.get(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
        )
        items = resp.json()
        assert items[0]["value"] == "s3cr3t"

    async def test_editor_sees_decrypted_secret(self, test_client, project, admin_token, editor_token):
        dev_id = _env_id(project, "development")
        await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="API_KEY", value="top-secret", config_type="secret",
        )
        resp = await test_client.get(
            _configs_url(project["id"], dev_id),
            headers=auth(editor_token),
        )
        items = resp.json()
        assert items[0]["value"] == "top-secret"

    async def test_non_secret_visible_to_all_roles(self, test_client, project, admin_token, viewer_token):
        dev_id = _env_id(project, "development")
        await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="APP_ENV", value="development", config_type="string",
        )
        resp = await test_client.get(
            _configs_url(project["id"], dev_id),
            headers=auth(viewer_token),
        )
        items = resp.json()
        assert items[0]["value"] == "development"
        assert items[0]["is_sensitive"] is False

    async def test_filter_by_config_type(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        pid = project["id"]
        await _make_config(test_client, admin_token, pid, dev_id, key="K1", value="v1", config_type="string")
        await _make_config(test_client, admin_token, pid, dev_id, key="K2", value="42", config_type="number")
        resp = await test_client.get(
            _configs_url(pid, dev_id),
            headers=auth(admin_token),
            params={"config_type": "number"},
        )
        items = resp.json()
        assert len(items) == 1
        assert items[0]["key"] == "K2"

    async def test_filter_by_search(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        pid = project["id"]
        await _make_config(test_client, admin_token, pid, dev_id, key="DATABASE_URL", value="v", config_type="string")
        await _make_config(test_client, admin_token, pid, dev_id, key="REDIS_URL", value="v", config_type="string")
        resp = await test_client.get(
            _configs_url(pid, dev_id),
            headers=auth(admin_token),
            params={"search": "DATABASE"},
        )
        items = resp.json()
        assert len(items) == 1
        assert items[0]["key"] == "DATABASE_URL"

    async def test_response_shape(self, test_client, project, admin_token, admin_user):
        dev_id = _env_id(project, "development")
        await _make_config(test_client, admin_token, project["id"], dev_id, key="SHAPE_TEST", value="val")
        resp = await test_client.get(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
        )
        item = resp.json()[0]
        assert "id" in item
        assert "key" in item
        assert "value" in item
        assert "config_type" in item
        assert "is_sensitive" in item
        assert "version" in item
        assert "created_by" in item
        assert "updated_by" in item
        assert "created_at" in item
        assert "updated_at" in item
        assert item["created_by"]["id"] == admin_user.id


# ══════════════════════════════════════════════════════════════════════════════
# POST /configs — create
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateConfig:
    async def test_admin_creates_string(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "APP_NAME", "value": "myapp", "config_type": "string"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["key"] == "APP_NAME"
        assert data["value"] == "myapp"
        assert data["config_type"] == "string"
        assert data["version"] == 1
        assert data["is_sensitive"] is False

    async def test_admin_creates_secret_encrypted_in_db(
        self, test_client, project, admin_token, db_session
    ):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "DB_PASS", "value": "plaintext", "config_type": "secret"},
        )
        assert resp.status_code == 201
        assert resp.json()["value"] == "plaintext"  # decrypted in response
        assert resp.json()["is_sensitive"] is True

        # Value should be encrypted in the DB
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "DB_PASS")
        )
        row = result.scalar_one()
        assert row.value != "plaintext"  # stored encrypted
        assert row.value.startswith("gAA")  # Fernet token

    async def test_admin_creates_number(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "MAX_CONN", "value": "100", "config_type": "number"},
        )
        assert resp.status_code == 201
        assert resp.json()["value"] == "100"

    async def test_admin_creates_boolean(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "VERBOSE", "value": "true", "config_type": "boolean"},
        )
        assert resp.status_code == 201

    async def test_admin_creates_json(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "SETTINGS", "value": '{"timeout": 30}', "config_type": "json"},
        )
        assert resp.status_code == 201

    async def test_admin_creates_feature_flag(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "NEW_UI", "value": "false", "config_type": "feature_flag"},
        )
        assert resp.status_code == 201

    async def test_editor_creates_in_dev(self, test_client, project, editor_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(editor_token),
            json={"key": "EDITOR_KEY", "value": "val", "config_type": "string"},
        )
        assert resp.status_code == 201

    async def test_editor_in_production_gets_202_approval(
        self, test_client, project, editor_token
    ):
        prod_id = _env_id(project, "production")
        resp = await test_client.post(
            _configs_url(project["id"], prod_id),
            headers=auth(editor_token),
            json={"key": "PROD_VAR", "value": "val", "config_type": "string"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "approval_request" in data
        ar = data["approval_request"]
        assert ar["status"] == "pending"
        assert ar["action"] == "create"
        assert ar["key"] == "PROD_VAR"

    async def test_editor_approval_no_config_created(
        self, test_client, project, editor_token, db_session
    ):
        prod_id = _env_id(project, "production")
        await test_client.post(
            _configs_url(project["id"], prod_id),
            headers=auth(editor_token),
            json={"key": "PENDING_VAR", "value": "val", "config_type": "string"},
        )
        # No ConfigEntry should exist yet
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "PENDING_VAR")
        )
        assert result.scalar_one_or_none() is None

    async def test_admin_creates_in_production_directly(
        self, test_client, project, admin_token
    ):
        prod_id = _env_id(project, "production")
        resp = await test_client.post(
            _configs_url(project["id"], prod_id),
            headers=auth(admin_token),
            json={"key": "ADMIN_PROD_VAR", "value": "val", "config_type": "string"},
        )
        assert resp.status_code == 201

    async def test_viewer_gets_403(self, test_client, project, viewer_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(viewer_token),
            json={"key": "K", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_gets_401(self, test_client, project):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            json={"key": "K", "value": "v", "config_type": "string"},
        )
        assert resp.status_code == 401

    async def test_duplicate_key_gets_409(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        await _make_config(test_client, admin_token, project["id"], dev_id, key="DUP_KEY")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "DUP_KEY", "value": "v2", "config_type": "string"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "DUPLICATE_RESOURCE"

    async def test_invalid_number_gets_422(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "BAD_NUM", "value": "not-a-number", "config_type": "number"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "INVALID_CONFIG_VALUE"

    async def test_invalid_boolean_gets_422(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "BAD_BOOL", "value": "yes", "config_type": "boolean"},
        )
        assert resp.status_code == 422

    async def test_invalid_json_gets_422(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
            json={"key": "BAD_JSON", "value": "{not valid json}", "config_type": "json"},
        )
        assert resp.status_code == 422

    async def test_creates_audit_log(self, test_client, project, admin_token, db_session):
        dev_id = _env_id(project, "development")
        await _make_config(
            test_client, admin_token, project["id"], dev_id, key="AUDIT_KEY"
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "config_created")
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.resource_type == "config"


# ══════════════════════════════════════════════════════════════════════════════
# PUT /configs/{config_id} — update
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateConfig:
    async def test_admin_updates_value(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id, key="UPD_KEY", value="old"
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
            json={"value": "new"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"] == "new"
        assert data["version"] == 2

    async def test_update_increments_version(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id, key="VER_KEY", value="v1"
        )
        for expected_version in (2, 3):
            resp = await test_client.put(
                _configs_url(project["id"], dev_id) + f"/{config['id']}",
                headers=auth(admin_token),
                json={"value": f"v{expected_version}"},
            )
            assert resp.status_code == 200
            assert resp.json()["version"] == expected_version

    async def test_update_description_only(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, admin_token, project["id"], dev_id, key="DESC_KEY")
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
            json={"description": "New description"},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "New description"

    async def test_update_secret_stays_encrypted_in_db(
        self, test_client, project, admin_token, db_session
    ):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="SEC_KEY", value="old_secret", config_type="secret",
        )
        await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
            json={"value": "new_secret"},
        )
        result = await db_session.execute(
            select(ConfigEntry).where(ConfigEntry.key == "SEC_KEY")
        )
        row = result.scalar_one()
        assert row.value.startswith("gAA")

    async def test_editor_updates_dev(self, test_client, project, editor_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, editor_token, project["id"], dev_id, key="E_KEY", value="old"
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(editor_token),
            json={"value": "new"},
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "new"

    async def test_editor_update_production_gets_202(
        self, test_client, project, admin_token, editor_token
    ):
        prod_id = _env_id(project, "production")
        # Admin creates it first
        config = await _make_config(
            test_client, admin_token, project["id"], prod_id, key="PROD_KEY", value="val"
        )
        resp = await test_client.put(
            _configs_url(project["id"], prod_id) + f"/{config['id']}",
            headers=auth(editor_token),
            json={"value": "new_val"},
        )
        assert resp.status_code == 202
        ar = resp.json()["approval_request"]
        assert ar["action"] == "update"
        assert ar["status"] == "pending"

    async def test_viewer_gets_403(self, test_client, project, admin_token, viewer_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, admin_token, project["id"], dev_id, key="V_KEY")
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(viewer_token),
            json={"value": "new"},
        )
        assert resp.status_code == 403

    async def test_config_not_found_gets_404(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + "/99999",
            headers=auth(admin_token),
            json={"value": "x"},
        )
        assert resp.status_code == 404

    async def test_invalid_type_value_gets_422(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id, key="NUM_KEY", value="10", config_type="number"
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
            json={"value": "not-a-number"},
        )
        assert resp.status_code == 422

    async def test_creates_audit_log(self, test_client, project, admin_token, db_session):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, admin_token, project["id"], dev_id, key="AUDIT_UPD")
        await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
            json={"value": "updated"},
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "config_updated")
        )
        log = result.scalar_one_or_none()
        assert log is not None


# ══════════════════════════════════════════════════════════════════════════════
# DELETE /configs/{config_id}
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteConfig:
    async def test_admin_deletes_from_dev(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, admin_token, project["id"], dev_id, key="DEL_KEY")
        resp = await test_client.delete(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
        )
        assert resp.status_code == 204

    async def test_admin_deletes_from_production(self, test_client, project, admin_token):
        prod_id = _env_id(project, "production")
        config = await _make_config(test_client, admin_token, project["id"], prod_id, key="PROD_DEL")
        resp = await test_client.delete(
            _configs_url(project["id"], prod_id) + f"/{config['id']}",
            headers=auth(admin_token),
        )
        assert resp.status_code == 204

    async def test_editor_deletes_from_dev(self, test_client, project, editor_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, editor_token, project["id"], dev_id, key="E_DEL_KEY")
        resp = await test_client.delete(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(editor_token),
        )
        assert resp.status_code == 204

    async def test_editor_cannot_delete_from_production(
        self, test_client, project, admin_token, editor_token
    ):
        prod_id = _env_id(project, "production")
        config = await _make_config(test_client, admin_token, project["id"], prod_id, key="PROD_KEEP")
        resp = await test_client.delete(
            _configs_url(project["id"], prod_id) + f"/{config['id']}",
            headers=auth(editor_token),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "FORBIDDEN"

    async def test_viewer_gets_403(self, test_client, project, admin_token, viewer_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, admin_token, project["id"], dev_id, key="V_DEL_KEY")
        resp = await test_client.delete(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_not_found_gets_404(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.delete(
            _configs_url(project["id"], dev_id) + "/99999",
            headers=auth(admin_token),
        )
        assert resp.status_code == 404

    async def test_config_gone_after_delete(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, admin_token, project["id"], dev_id, key="GONE_KEY")
        await test_client.delete(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
        )
        # List should be empty now
        resp = await test_client.get(
            _configs_url(project["id"], dev_id),
            headers=auth(admin_token),
        )
        assert resp.json() == []

    async def test_creates_audit_log(self, test_client, project, admin_token, db_session):
        dev_id = _env_id(project, "development")
        config = await _make_config(test_client, admin_token, project["id"], dev_id, key="AUDIT_DEL")
        await test_client.delete(
            _configs_url(project["id"], dev_id) + f"/{config['id']}",
            headers=auth(admin_token),
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "config_deleted")
        )
        log = result.scalar_one_or_none()
        assert log is not None


# ══════════════════════════════════════════════════════════════════════════════
# POST /configs/{config_id}/reveal
# ══════════════════════════════════════════════════════════════════════════════

class TestRevealSecret:
    async def test_admin_can_reveal(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="MY_SECRET", value="ultra-secret", config_type="secret",
        )
        resp = await test_client.post(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/reveal",
            headers=auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "ultra-secret"

    async def test_editor_can_reveal(self, test_client, project, admin_token, editor_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="EDITOR_SECRET", value="editor-can-see", config_type="secret",
        )
        resp = await test_client.post(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/reveal",
            headers=auth(editor_token),
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "editor-can-see"

    async def test_viewer_gets_403(self, test_client, project, admin_token, viewer_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="VIEWER_SECRET", value="hidden", config_type="secret",
        )
        resp = await test_client.post(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/reveal",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_non_secret_gets_400(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="PLAIN_VAR", value="plain", config_type="string",
        )
        resp = await test_client.post(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/reveal",
            headers=auth(admin_token),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_CONFIG_VALUE"

    async def test_not_found_gets_404(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.post(
            _configs_url(project["id"], dev_id) + "/99999/reveal",
            headers=auth(admin_token),
        )
        assert resp.status_code == 404

    async def test_creates_secret_accessed_audit_log(
        self, test_client, project, admin_token, db_session
    ):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="AUDIT_SECRET", value="val", config_type="secret",
        )
        await test_client.post(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/reveal",
            headers=auth(admin_token),
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "secret_accessed")
        )
        log = result.scalar_one_or_none()
        assert log is not None
        import json
        details = json.loads(log.details)
        assert "value not logged" in details.get("note", "")


# ══════════════════════════════════════════════════════════════════════════════
# PUT /configs/{config_id}/toggle
# ══════════════════════════════════════════════════════════════════════════════

class TestToggleFeatureFlag:
    async def test_admin_toggles_false_to_true(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="FF_1", value="false", config_type="feature_flag",
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/toggle",
            headers=auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "true"

    async def test_admin_toggles_true_to_false(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="FF_2", value="true", config_type="feature_flag",
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/toggle",
            headers=auth(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "false"

    async def test_toggle_increments_version(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="FF_VER", value="false", config_type="feature_flag",
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/toggle",
            headers=auth(admin_token),
        )
        assert resp.json()["version"] == 2

    async def test_editor_toggles_in_dev(self, test_client, project, editor_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, editor_token, project["id"], dev_id,
            key="E_FF", value="false", config_type="feature_flag",
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/toggle",
            headers=auth(editor_token),
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "true"

    async def test_editor_toggle_production_gets_202(
        self, test_client, project, admin_token, editor_token
    ):
        prod_id = _env_id(project, "production")
        config = await _make_config(
            test_client, admin_token, project["id"], prod_id,
            key="PROD_FF", value="false", config_type="feature_flag",
        )
        resp = await test_client.put(
            _configs_url(project["id"], prod_id) + f"/{config['id']}/toggle",
            headers=auth(editor_token),
        )
        assert resp.status_code == 202
        ar = resp.json()["approval_request"]
        assert ar["proposed_value"] == "true"
        assert ar["current_value"] == "false"
        assert ar["action"] == "update"

    async def test_viewer_gets_403(self, test_client, project, admin_token, viewer_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="V_FF", value="true", config_type="feature_flag",
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/toggle",
            headers=auth(viewer_token),
        )
        assert resp.status_code == 403

    async def test_non_feature_flag_gets_400(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        config = await _make_config(
            test_client, admin_token, project["id"], dev_id,
            key="PLAIN_STR", value="hello", config_type="string",
        )
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + f"/{config['id']}/toggle",
            headers=auth(admin_token),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INVALID_CONFIG_VALUE"

    async def test_not_found_gets_404(self, test_client, project, admin_token):
        dev_id = _env_id(project, "development")
        resp = await test_client.put(
            _configs_url(project["id"], dev_id) + "/99999/toggle",
            headers=auth(admin_token),
        )
        assert resp.status_code == 404

    async def test_approval_audit_log_created(
        self, test_client, project, admin_token, editor_token, db_session
    ):
        prod_id = _env_id(project, "production")
        config = await _make_config(
            test_client, admin_token, project["id"], prod_id,
            key="AUDIT_FF", value="false", config_type="feature_flag",
        )
        await test_client.put(
            _configs_url(project["id"], prod_id) + f"/{config['id']}/toggle",
            headers=auth(editor_token),
        )
        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "approval_requested")
        )
        log = result.scalar_one_or_none()
        assert log is not None
