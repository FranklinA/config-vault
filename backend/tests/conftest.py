"""
Shared fixtures for all test modules.

Architecture:
  - test_engine  : function-scoped in-memory SQLite with StaticPool
                   (all sessions share one connection → data visible across sessions)
  - mock_redis   : patches the global cache singleton with FakeRedis
  - test_client  : AsyncClient with get_db + cache overridden
  - *_user       : pre-committed User rows created directly in the test engine
  - *_token      : JWTs generated from the user fixtures
"""
from datetime import datetime, timedelta, timezone

import fakeredis.aioredis
import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.cache import cache
from app.config import JWT_ALGORITHM, JWT_SECRET_KEY
from app.database import Base
from app.dependencies import get_db
from app.main import app
from app.models import User
from app.security import create_access_token, hash_password

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


# ─── Engine ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_engine():
    """Fresh in-memory SQLite DB per test, all sessions share the same connection."""
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ─── Fake Redis ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def mock_redis():
    """Replaces the global CacheManager with an in-process FakeRedis."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    original_client = cache._client
    original_available = cache._available
    cache._client = fake
    cache._available = True

    yield fake

    cache._client = original_client
    cache._available = original_available
    try:
        await fake.aclose()
    except Exception:
        pass


# ─── DB session (for direct queries inside tests) ─────────────────────────────

@pytest_asyncio.fixture
async def db_session(test_engine):
    """Raw async session for asserting DB state in tests."""
    SessionLocal = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with SessionLocal() as session:
        yield session


# ─── HTTP client with dependency overrides ────────────────────────────────────

@pytest_asyncio.fixture
async def test_client(test_engine, mock_redis):
    """AsyncClient wired to the FastAPI app with test DB and fake Redis."""
    TestSessionLocal = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ─── User factory ─────────────────────────────────────────────────────────────

async def _make_user(
    engine,
    name: str,
    email: str,
    password: str,
    role: str,
    is_active: bool = True,
) -> User:
    """Insert a User directly into the test DB and return the ORM object."""
    SessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with SessionLocal() as session:
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(test_engine) -> User:
    return await _make_user(test_engine, "Admin User", "admin@test.local", "admin123", "admin")


@pytest_asyncio.fixture
async def editor_user(test_engine) -> User:
    return await _make_user(test_engine, "Editor User", "editor@test.local", "editor123", "editor")


@pytest_asyncio.fixture
async def viewer_user(test_engine) -> User:
    return await _make_user(test_engine, "Viewer User", "viewer@test.local", "viewer123", "viewer")


# ─── Token factory ────────────────────────────────────────────────────────────

@pytest.fixture
def admin_token(admin_user) -> str:
    return create_access_token(admin_user.id, admin_user.email, admin_user.role)


@pytest.fixture
def editor_token(editor_user) -> str:
    return create_access_token(editor_user.id, editor_user.email, editor_user.role)


@pytest.fixture
def viewer_token(viewer_user) -> str:
    return create_access_token(viewer_user.id, viewer_user.email, viewer_user.role)


# ─── Helper: expired token ────────────────────────────────────────────────────

def make_expired_token(user_id: int, email: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
