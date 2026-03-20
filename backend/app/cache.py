import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.config import REDIS_URL

logger = logging.getLogger(__name__)

_BLACKLIST_PREFIX = "blacklist:"
_CONFIGS_PREFIX = "configs:"
_CONFIGS_TTL = 300  # 5 minutes


class CacheManager:
    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None
        self._available: bool = False

    async def connect(self) -> None:
        try:
            self._client = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await self._client.ping()
            self._available = True
            logger.info("Redis connected at %s", REDIS_URL)
        except Exception as exc:
            self._available = False
            self._client = None
            logger.warning("Redis unavailable (%s). Running without cache.", exc)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
            self._available = False

    # ── Primitives ─────────────────────────────────────────────────────────────

    async def get(self, key: str) -> str | None:
        if not self._available or self._client is None:
            return None
        try:
            return await self._client.get(key)
        except Exception as exc:
            logger.warning("Redis GET error: %s", exc)
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if not self._available or self._client is None:
            return False
        try:
            await self._client.set(key, value, ex=ttl)
            return True
        except Exception as exc:
            logger.warning("Redis SET error: %s", exc)
            return False

    async def delete(self, key: str) -> bool:
        if not self._available or self._client is None:
            return False
        try:
            await self._client.delete(key)
            return True
        except Exception as exc:
            logger.warning("Redis DELETE error: %s", exc)
            return False

    # ── Token blacklist ────────────────────────────────────────────────────────

    async def blacklist_token(self, token: str, ttl_seconds: int) -> None:
        """Add a JWT to the revocation blacklist. Silently skips if Redis is down."""
        if ttl_seconds <= 0:
            return
        await self.set(f"{_BLACKLIST_PREFIX}{token}", "1", ttl=ttl_seconds)

    async def is_blacklisted(self, token: str) -> bool:
        """Returns True if the token has been revoked. Returns False if Redis is down."""
        value = await self.get(f"{_BLACKLIST_PREFIX}{token}")
        return value is not None

    # ── Config cache ───────────────────────────────────────────────────────────

    async def get_configs(self, project_id: int, env_id: int) -> list | None:
        """Return cached config list for the environment, or None on miss/error."""
        raw = await self.get(f"{_CONFIGS_PREFIX}{project_id}:{env_id}")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Cache get_configs decode error: %s", exc)
            return None

    async def set_configs(self, project_id: int, env_id: int, data: list) -> None:
        """Cache a serialisable config list. Silently skips if Redis is down."""
        try:
            await self.set(
                f"{_CONFIGS_PREFIX}{project_id}:{env_id}",
                json.dumps(data, default=str),
                ttl=_CONFIGS_TTL,
            )
        except Exception as exc:
            logger.warning("Cache set_configs error: %s", exc)

    async def invalidate_configs(self, project_id: int, env_id: int) -> None:
        """Remove the config cache entry for the environment."""
        await self.delete(f"{_CONFIGS_PREFIX}{project_id}:{env_id}")


cache = CacheManager()
