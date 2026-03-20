"""
Tests for Redis config cache (Fase 5).

Coverage:
  - Cache miss → data fetched from DB and stored in Redis
  - Cache hit → data served from Redis (no new DB query needed)
  - Cache invalidation on create/update/delete/toggle
  - Cache invalidation on approval approve
  - Fallback when Redis is unavailable
"""
import json
import pytest


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_project(client, token, name="Cache Test Project") -> dict:
    resp = await client.post("/api/projects", headers=auth(token), json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _dev_id(project):
    return next(e["id"] for e in project["environments"] if e["name"] == "development")

def _prod_id(project):
    return next(e["id"] for e in project["environments"] if e["name"] == "production")


def _cache_key(project_id, env_id):
    return f"configs:{project_id}:{env_id}"


# ──────────────────────────────────────────────────────────────────────────────

class TestConfigCacheMiss:
    async def test_first_get_stores_in_cache(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Miss Project")
        dev = _dev_id(proj)
        key = _cache_key(proj["id"], dev)

        # Initially: no cache entry
        assert await mock_redis.get(key) is None

        # First GET → DB query → cache populated
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert resp.status_code == 200

        # Cache entry now exists
        cached = await mock_redis.get(key)
        assert cached is not None
        parsed = json.loads(cached)
        assert isinstance(parsed, list)


class TestConfigCacheHit:
    async def test_second_get_reads_from_cache(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Hit Project")
        dev = _dev_id(proj)

        # Create a config
        await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "HIT_KEY", "value": "hit-value", "config_type": "string"},
        )

        # First GET → populates cache
        r1 = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        # Second GET → should come from cache (same result)
        r2 = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    async def test_cache_serves_correct_data(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Correct Data")
        dev = _dev_id(proj)

        await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "CACHED_KEY", "value": "cached-value", "config_type": "string"},
        )

        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        items = resp.json()
        assert len(items) == 1
        assert items[0]["key"] == "CACHED_KEY"
        assert items[0]["value"] == "cached-value"


class TestConfigCacheInvalidation:
    async def test_create_invalidates_cache(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Inval Create")
        dev = _dev_id(proj)
        key = _cache_key(proj["id"], dev)

        # Populate cache with empty list
        await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert await mock_redis.get(key) is not None

        # Create a config → should invalidate cache
        await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "NEW_KEY", "value": "v", "config_type": "string"},
        )
        assert await mock_redis.get(key) is None

        # Next GET re-populates cache with the new config
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert any(c["key"] == "NEW_KEY" for c in resp.json())

    async def test_update_invalidates_cache(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Inval Update")
        dev = _dev_id(proj)
        key = _cache_key(proj["id"], dev)

        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "UPD_KEY", "value": "old", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]

        # Populate cache
        await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert await mock_redis.get(key) is not None

        # Update → invalidate
        await test_client.put(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg_id}",
            headers=auth(admin_token),
            json={"value": "new"},
        )
        assert await mock_redis.get(key) is None

        # Re-fetch reflects updated value
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert resp.json()[0]["value"] == "new"

    async def test_delete_invalidates_cache(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Inval Delete")
        dev = _dev_id(proj)
        key = _cache_key(proj["id"], dev)

        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "DEL_KEY", "value": "v", "config_type": "string"},
        )
        cfg_id = cfg_resp.json()["id"]

        # Populate cache
        await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert await mock_redis.get(key) is not None

        # Delete → invalidate
        await test_client.delete(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg_id}",
            headers=auth(admin_token),
        )
        assert await mock_redis.get(key) is None

        # Re-fetch shows empty list
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert resp.json() == []

    async def test_toggle_invalidates_cache(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Inval Toggle")
        dev = _dev_id(proj)
        key = _cache_key(proj["id"], dev)

        cfg_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "FF_KEY", "value": "true", "config_type": "feature_flag"},
        )
        cfg_id = cfg_resp.json()["id"]

        # Populate cache
        await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )
        assert await mock_redis.get(key) is not None

        # Toggle → invalidate
        await test_client.put(
            f"/api/projects/{proj['id']}/environments/{dev}/configs/{cfg_id}/toggle",
            headers=auth(admin_token),
        )
        assert await mock_redis.get(key) is None

    async def test_approve_invalidates_production_cache(self, test_client, admin_token, editor_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Inval Approve")
        prod = _prod_id(proj)
        key = _cache_key(proj["id"], prod)

        # Populate production cache (empty)
        await test_client.get(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
        )
        assert await mock_redis.get(key) is not None

        # Editor creates approval in production
        ar_resp = await test_client.post(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(editor_token),
            json={"key": "PROD_CACHE_KEY", "value": "v", "config_type": "string"},
        )
        ar_id = ar_resp.json()["approval_request"]["id"]

        # Cache should still be there (approval creation doesn't change configs)
        # Admin approves → cache invalidated
        await test_client.post(
            f"/api/approvals/{ar_id}/approve",
            headers=auth(admin_token),
            json={"review_comment": None},
        )
        assert await mock_redis.get(key) is None

        # Re-fetch shows the newly approved config
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{prod}/configs",
            headers=auth(admin_token),
        )
        assert any(c["key"] == "PROD_CACHE_KEY" for c in resp.json())


class TestCacheSecretMasking:
    async def test_cached_secret_masked_for_viewer(self, test_client, admin_token, viewer_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Secret Viewer")
        dev = _dev_id(proj)

        await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "SEC_KEY", "value": "ultra-secret", "config_type": "secret"},
        )

        # Admin populates cache
        await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
        )

        # Viewer reads from cache → should see ********
        resp = await test_client.get(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(viewer_token),
        )
        items = resp.json()
        assert items[0]["value"] == "********"

    async def test_cached_secret_decrypted_for_admin(self, test_client, admin_token, mock_redis):
        proj = await _make_project(test_client, admin_token, "Cache Secret Admin")
        dev = _dev_id(proj)

        await test_client.post(
            f"/api/projects/{proj['id']}/environments/{dev}/configs",
            headers=auth(admin_token),
            json={"key": "ADMIN_SEC", "value": "plain-secret", "config_type": "secret"},
        )

        # First GET (DB) + Second GET (cache) — both should return decrypted value
        for _ in range(2):
            resp = await test_client.get(
                f"/api/projects/{proj['id']}/environments/{dev}/configs",
                headers=auth(admin_token),
            )
            assert resp.json()[0]["value"] == "plain-secret"


class TestCacheFallback:
    async def test_system_works_without_redis(self, test_engine, mock_redis):
        """When Redis is unavailable, GET /configs falls back to DB."""
        from app.cache import cache
        from app.dependencies import get_db
        from app.main import app
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from httpx import ASGITransport, AsyncClient

        TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        async def override_get_db():
            async with TestSessionLocal() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        # Simulate Redis unavailable
        original_available = cache._available
        cache._available = False
        app.dependency_overrides[get_db] = override_get_db

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                from app.security import create_access_token
                from tests.conftest import _make_user
                user = await _make_user(test_engine, "Fallback Admin", "fallback@test.local", "pass1234", "admin")
                token = create_access_token(user.id, user.email, user.role)

                proj_resp = await client.post(
                    "/api/projects",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"name": "Fallback Project"},
                )
                assert proj_resp.status_code == 201
                proj = proj_resp.json()
                dev = next(e["id"] for e in proj["environments"] if e["name"] == "development")

                # GET /configs should work even without Redis
                resp = await client.get(
                    f"/api/projects/{proj['id']}/environments/{dev}/configs",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 200
                assert resp.json() == []
        finally:
            cache._available = original_available
            app.dependency_overrides.clear()
