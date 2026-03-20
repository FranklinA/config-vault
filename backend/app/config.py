import os
from cryptography.fernet import Fernet


def _get_fernet_key() -> str:
    key = os.getenv("FERNET_KEY")
    if not key:
        key = Fernet.generate_key().decode()
    return key


JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM: str = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

FERNET_KEY: str = _get_fernet_key()

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./config_vault.db")
