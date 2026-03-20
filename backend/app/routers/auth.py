from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import create_audit_log
from app.cache import cache
from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import LoginRequest, PasswordChange, TokenResponse, UserResponse
from app.security import (
    create_access_token,
    get_token_remaining_seconds,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ─── POST /api/auth/login ─────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        if user is not None:
            await create_audit_log(
                db,
                user_id=user.id,
                action="login_failed",
                resource_type="user",
                resource_id=user.id,
                details={"email": body.email, "reason": "invalid_credentials"},
                ip_address=ip,
            )
            # Commit the audit log now — HTTPException will trigger a rollback
            # in get_db's cleanup, so we must persist the log before raising.
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password.", "field": None},
        )

    token = create_access_token(user.id, user.email, user.role)

    await create_audit_log(
        db,
        user_id=user.id,
        action="login",
        resource_type="user",
        resource_id=user.id,
        details={"email": user.email},
        ip_address=ip,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


# ─── POST /api/auth/logout ────────────────────────────────────────────────────

@router.post("/logout")
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if credentials:
        token = credentials.credentials
        ttl = get_token_remaining_seconds(token)
        await cache.blacklist_token(token, ttl)

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="logout",
        resource_type="user",
        resource_id=current_user.id,
        details={"email": current_user.email},
        ip_address=_client_ip(request),
    )

    return {"message": "Logged out successfully"}


# ─── GET /api/auth/me ─────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def me(current_user: UserResponse = Depends(get_current_user)):
    return current_user


# ─── PUT /api/auth/me/password ────────────────────────────────────────────────

@router.put("/me/password")
async def change_password(
    body: PasswordChange,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CREDENTIALS", "message": "Current password is incorrect.", "field": "current_password"},
        )

    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CONFIG_VALUE", "message": "New password must differ from current password.", "field": "new_password"},
        )

    user.password_hash = hash_password(body.new_password)

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="user_updated",
        resource_type="user",
        resource_id=current_user.id,
        details={"change": "password"},
        ip_address=_client_ip(request),
    )

    return {"message": "Password updated successfully"}
