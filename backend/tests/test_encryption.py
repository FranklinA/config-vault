"""
Unit tests for app/encryption.py — Fernet symmetric encryption.

Covers: encrypt, decrypt, is_encrypted, round-trips, error cases, edge values.
No HTTP calls — pure unit tests of the encryption module.
"""
import pytest
from cryptography.fernet import InvalidToken

from app.encryption import decrypt, encrypt, is_encrypted


# ══════════════════════════════════════════════════════════════════════════════
# encrypt()
# ══════════════════════════════════════════════════════════════════════════════

class TestEncrypt:
    def test_returns_string(self):
        assert isinstance(encrypt("hello"), str)

    def test_result_starts_with_gAA(self):
        """All Fernet tokens begin with gAA (base64url of version byte)."""
        assert encrypt("hello").startswith("gAA")

    def test_non_deterministic(self):
        """Fernet uses a random IV — same plaintext produces different tokens."""
        r1 = encrypt("hello")
        r2 = encrypt("hello")
        assert r1 != r2

    def test_empty_string(self):
        token = encrypt("")
        assert token.startswith("gAA")

    def test_long_string(self):
        long = "x" * 100_000
        token = encrypt(long)
        assert token.startswith("gAA")

    def test_special_characters(self):
        special = r"""!@#$%^&*()_+-=[]{}|;':",./<>?`~"""
        assert encrypt(special).startswith("gAA")

    def test_unicode_string(self):
        assert encrypt("Hello, 世界! 🔐").startswith("gAA")

    def test_newlines_and_whitespace(self):
        assert encrypt("line1\nline2\ttab").startswith("gAA")

    def test_json_like_value(self):
        assert encrypt('{"key": "value", "num": 42}').startswith("gAA")

    def test_url_like_value(self):
        assert encrypt("postgres://user:pass@host:5432/db").startswith("gAA")

    def test_returns_url_safe_base64(self):
        """Fernet output must be URL-safe base64 with no padding issues."""
        token = encrypt("test")
        # Should not contain characters that break URL query params
        assert "+" not in token
        assert "/" not in token

    def test_different_inputs_different_outputs(self):
        t1 = encrypt("secret1")
        t2 = encrypt("secret2")
        assert t1 != t2


# ══════════════════════════════════════════════════════════════════════════════
# decrypt()
# ══════════════════════════════════════════════════════════════════════════════

class TestDecrypt:
    def test_round_trip_basic(self):
        plaintext = "my-secret-value"
        assert decrypt(encrypt(plaintext)) == plaintext

    def test_round_trip_empty_string(self):
        assert decrypt(encrypt("")) == ""

    def test_round_trip_unicode(self):
        s = "Hello, 世界! 🔐 Ñoño"
        assert decrypt(encrypt(s)) == s

    def test_round_trip_special_chars(self):
        s = r"""!@#$%^&*()_+-=[]{}|;':",./<>?`~"""
        assert decrypt(encrypt(s)) == s

    def test_round_trip_multiline(self):
        s = "line1\nline2\nline3"
        assert decrypt(encrypt(s)) == s

    def test_round_trip_long_string(self):
        s = "a" * 50_000
        assert decrypt(encrypt(s)) == s

    def test_round_trip_json(self):
        s = '{"timeout": 30, "retry": true, "host": "localhost"}'
        assert decrypt(encrypt(s)) == s

    def test_round_trip_url(self):
        s = "postgres://admin:s3cr3t@db.internal:5432/production"
        assert decrypt(encrypt(s)) == s

    def test_multiple_encrypt_same_decrypt(self):
        """Multiple encryptions of the same value all decrypt to the same plaintext."""
        plaintext = "consistent-value"
        for _ in range(10):
            assert decrypt(encrypt(plaintext)) == plaintext

    def test_invalid_token_raises(self):
        with pytest.raises(Exception):
            decrypt("not-a-valid-fernet-token")

    def test_plaintext_raises(self):
        with pytest.raises(Exception):
            decrypt("DATABASE_URL=postgres://localhost/mydb")

    def test_empty_string_raises(self):
        with pytest.raises(Exception):
            decrypt("")

    def test_tampered_token_raises(self):
        """Modifying the token (even a single char) must fail validation."""
        token = encrypt("secret")
        tampered = token[:-4] + "XXXX"
        with pytest.raises(Exception):
            decrypt(tampered)

    def test_truncated_token_raises(self):
        token = encrypt("secret")
        with pytest.raises(Exception):
            decrypt(token[:20])

    def test_random_base64_raises(self):
        import base64
        fake = base64.urlsafe_b64encode(b"x" * 64).decode()
        with pytest.raises(Exception):
            decrypt(fake)

    def test_almost_valid_prefix_raises(self):
        """Even a string starting with 'gAA' but otherwise invalid must fail."""
        with pytest.raises(Exception):
            decrypt("gAABBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB=")


# ══════════════════════════════════════════════════════════════════════════════
# is_encrypted()
# ══════════════════════════════════════════════════════════════════════════════

class TestIsEncrypted:
    def test_real_fernet_token_returns_true(self):
        assert is_encrypted(encrypt("hello")) is True

    def test_plain_string_returns_false(self):
        assert is_encrypted("hello") is False

    def test_empty_string_returns_false(self):
        assert is_encrypted("") is False

    def test_connection_string_returns_false(self):
        assert is_encrypted("postgres://localhost/db") is False

    def test_json_returns_false(self):
        assert is_encrypted('{"key": "value"}') is False

    def test_true_string_returns_false(self):
        assert is_encrypted("true") is False

    def test_false_string_returns_false(self):
        assert is_encrypted("false") is False

    def test_numeric_string_returns_false(self):
        assert is_encrypted("12345") is False

    def test_url_returns_false(self):
        assert is_encrypted("https://example.com/api") is False

    def test_gAA_prefix_is_the_marker(self):
        """The heuristic is based on the 'gAA' prefix."""
        assert is_encrypted("gAAAAAA") is True  # starts with gAA
        assert is_encrypted("hAAAAAAA") is False

    def test_multiple_encrypted_values(self):
        """Consistency: encrypt always produces tokens that pass is_encrypted."""
        for value in ["abc", "123", "secret!", '{"k":"v"}', ""]:
            assert is_encrypted(encrypt(value)) is True

    def test_partial_prefix_returns_false(self):
        assert is_encrypted("gA") is False
        assert is_encrypted("g") is False
        assert is_encrypted("gAB") is False


# ══════════════════════════════════════════════════════════════════════════════
# Integration: encryption in config storage (via DB via API)
# ══════════════════════════════════════════════════════════════════════════════

class TestEncryptionInStorage:
    """Verify that secrets are encrypted at rest and decrypted in API responses."""

    async def test_secret_stored_encrypted_in_db(self, test_client, admin_token, admin_user, db_session):
        from sqlalchemy import select
        from app.models import ConfigEntry

        proj = await test_client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Enc Storage Test"},
        )
        assert proj.status_code == 201
        proj_data = proj.json()
        dev_id = next(e["id"] for e in proj_data["environments"] if e["name"] == "development")

        await test_client.post(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"key": "MY_SECRET", "value": "plaintext-secret", "config_type": "secret"},
        )

        # DB stores encrypted value
        result = await db_session.execute(select(ConfigEntry).where(ConfigEntry.key == "MY_SECRET"))
        row = result.scalar_one()
        assert row.value != "plaintext-secret"
        assert is_encrypted(row.value)

    async def test_secret_decrypted_for_admin_in_response(self, test_client, admin_token):
        proj = await test_client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Enc Response Admin"},
        )
        proj_data = proj.json()
        dev_id = next(e["id"] for e in proj_data["environments"] if e["name"] == "development")

        await test_client.post(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"key": "ADMIN_SEC", "value": "visible-to-admin", "config_type": "secret"},
        )

        resp = await test_client.get(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        item = next(c for c in resp.json() if c["key"] == "ADMIN_SEC")
        assert item["value"] == "visible-to-admin"

    async def test_secret_masked_for_viewer_in_response(self, test_client, admin_token, viewer_token):
        proj = await test_client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Enc Response Viewer"},
        )
        proj_data = proj.json()
        dev_id = next(e["id"] for e in proj_data["environments"] if e["name"] == "development")

        await test_client.post(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"key": "VIEWER_SEC", "value": "hidden-from-viewer", "config_type": "secret"},
        )

        resp = await test_client.get(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        item = next(c for c in resp.json() if c["key"] == "VIEWER_SEC")
        assert item["value"] == "********"
        assert item["is_sensitive"] is True

    async def test_reveal_endpoint_returns_plaintext(self, test_client, admin_token):
        proj = await test_client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Enc Reveal Test"},
        )
        proj_data = proj.json()
        dev_id = next(e["id"] for e in proj_data["environments"] if e["name"] == "development")

        cfg = await test_client.post(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"key": "REVEAL_ME", "value": "revealed-value", "config_type": "secret"},
        )
        cfg_id = cfg.json()["id"]

        resp = await test_client.post(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs/{cfg_id}/reveal",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "revealed-value"

    async def test_update_secret_reencrypts(self, test_client, admin_token, db_session):
        from sqlalchemy import select
        from app.models import ConfigEntry

        proj = await test_client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "Enc Update Test"},
        )
        proj_data = proj.json()
        dev_id = next(e["id"] for e in proj_data["environments"] if e["name"] == "development")

        cfg = await test_client.post(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"key": "UPD_SECRET", "value": "old-secret", "config_type": "secret"},
        )
        cfg_id = cfg.json()["id"]

        await test_client.put(
            f"/api/projects/{proj_data['id']}/environments/{dev_id}/configs/{cfg_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"value": "new-secret"},
        )

        result = await db_session.execute(select(ConfigEntry).where(ConfigEntry.id == cfg_id))
        row = result.scalar_one()
        # Still encrypted, and decrypts to the NEW value
        assert is_encrypted(row.value)
        assert decrypt(row.value) == "new-secret"
