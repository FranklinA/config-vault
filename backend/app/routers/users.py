from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import create_audit_log
from app.dependencies import get_current_user, get_db, require_role
from app.models import User
from pydantic import BaseModel, Field

from app.schemas import UserCreate, UserResponse
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ─── GET /api/users ───────────────────────────────────────────────────────────

@router.get("", dependencies=[Depends(require_role("admin"))])
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)

    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        query = query.where(User.name.ilike(pattern) | User.email.ilike(pattern))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar_one()

    query = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "data": [UserResponse.model_validate(u) for u in users],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, -(-total // per_page)),  # ceiling division
        },
    }


# ─── POST /api/users ──────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def create_user(
    body: UserCreate,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "DUPLICATE_RESOURCE", "message": "A user with this email already exists.", "field": "email"},
        )

    user = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="user_created",
        resource_type="user",
        resource_id=user.id,
        details={"name": user.name, "email": user.email, "role": user.role},
        ip_address=_client_ip(request),
    )

    await db.refresh(user)
    return UserResponse.model_validate(user)


# ─── PUT /api/users/{id} ──────────────────────────────────────────────────────

class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    role: str | None = Field(None, pattern="^(admin|editor|viewer)$")
    is_active: bool | None = None


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "User not found.", "field": None},
        )

    # Guard: admin cannot deactivate or change role of themselves
    if user_id == current_user.id:
        if body.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "FORBIDDEN", "message": "You cannot deactivate your own account.", "field": "is_active"},
            )
        if body.role is not None and body.role != current_user.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "FORBIDDEN", "message": "You cannot change your own role.", "field": "role"},
            )

    changes: dict = {}
    if body.name is not None and body.name != user.name:
        changes["name"] = {"old": user.name, "new": body.name}
        user.name = body.name
    if body.role is not None and body.role != user.role:
        changes["role"] = {"old": user.role, "new": body.role}
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = {"old": user.is_active, "new": body.is_active}
        user.is_active = body.is_active

    if changes:
        await create_audit_log(
            db,
            user_id=current_user.id,
            action="user_updated",
            resource_type="user",
            resource_id=user.id,
            details={"changes": changes, "target_email": user.email},
            ip_address=_client_ip(request),
        )

    await db.flush()
    await db.refresh(user)
    return UserResponse.model_validate(user)
