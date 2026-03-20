"""
seed.py — Creates the initial admin user.
Run from the backend/ directory:
    python seed.py
"""
import asyncio
import sys

from sqlalchemy import select

sys.path.insert(0, ".")

from app.database import AsyncSessionLocal, create_tables
from app.models import User
from app.security import hash_password


ADMIN_NAME = "Admin"
ADMIN_EMAIL = "admin@configvault.local"
ADMIN_PASSWORD = "admin123"


async def seed() -> None:
    await create_tables()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[seed] Admin user already exists (id={existing.id}). Skipping.")
            return

        admin = User(
            name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        print(f"[seed] Admin user created successfully.")
        print(f"       id    : {admin.id}")
        print(f"       email : {admin.email}")
        print(f"       role  : {admin.role}")


if __name__ == "__main__":
    asyncio.run(seed())
