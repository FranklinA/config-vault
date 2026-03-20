from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import create_audit_log
from app.dependencies import get_current_user, get_db, require_role
from app.encryption import decrypt
from app.models import ApprovalRequest, ConfigEntry, Environment
from app.schemas import ApprovalReview, UserResponse

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

MASKED = "********"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _load_ar(db: AsyncSession, ar_id: int) -> ApprovalRequest | None:
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == ar_id)
        .options(
            selectinload(ApprovalRequest.environment).selectinload(Environment.project),
            selectinload(ApprovalRequest.requester),
            selectinload(ApprovalRequest.reviewer),
        )
    )
    return result.scalar_one_or_none()


def _expose(value: str | None, config_type: str, role: str) -> str | None:
    """Decrypt secret values; mask them for viewers."""
    if value is None:
        return None
    if config_type != "secret":
        return value
    if role == "viewer":
        return MASKED
    try:
        return decrypt(value)
    except Exception:
        return MASKED


def _ar_dict(ar: ApprovalRequest, role: str) -> dict:
    env = ar.environment
    project = env.project
    return {
        "id": ar.id,
        "config_entry_id": ar.config_entry_id,
        "environment": {"id": env.id, "name": env.name},
        "project": {"id": project.id, "name": project.name},
        "action": ar.action,
        "key": ar.key,
        "proposed_value": _expose(ar.proposed_value, ar.config_type, role),
        "config_type": ar.config_type,
        "current_value": _expose(ar.current_value, ar.config_type, role),
        "status": ar.status,
        "requested_by": {"id": ar.requester.id, "name": ar.requester.name},
        "reviewed_by": {"id": ar.reviewer.id, "name": ar.reviewer.name} if ar.reviewer else None,
        "review_comment": ar.review_comment,
        "created_at": ar.created_at,
        "reviewed_at": ar.reviewed_at,
    }


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": "Approval request not found.", "field": None},
    )


def _forbidden(msg: str = "You don't have permission to perform this action.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "FORBIDDEN", "message": msg, "field": None},
    )


def _conflict(msg: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "CONFLICT", "message": msg, "field": None},
    )


# ─── GET /api/approvals ───────────────────────────────────────────────────────

@router.get("")
async def list_approvals(
    status_filter: str | None = Query(None, alias="status"),
    project_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    base = select(ApprovalRequest)

    if current_user.role == "editor":
        base = base.where(ApprovalRequest.requested_by == current_user.id)

    if status_filter:
        base = base.where(ApprovalRequest.status == status_filter)

    if project_id is not None:
        base = base.join(Environment, ApprovalRequest.environment_id == Environment.id).where(
            Environment.project_id == project_id
        )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    data_query = (
        base.options(
            selectinload(ApprovalRequest.environment).selectinload(Environment.project),
            selectinload(ApprovalRequest.requester),
            selectinload(ApprovalRequest.reviewer),
        )
        .order_by(ApprovalRequest.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    rows = (await db.execute(data_query)).scalars().all()
    data = [_ar_dict(ar, current_user.role) for ar in rows]

    return {
        "data": jsonable_encoder(data),
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, -(-total // per_page)),
        },
    }


# ─── GET /api/approvals/{id} ──────────────────────────────────────────────────

@router.get("/{ar_id}")
async def get_approval(
    ar_id: int,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    ar = await _load_ar(db, ar_id)
    if ar is None:
        raise _not_found()

    if current_user.role == "editor" and ar.requested_by != current_user.id:
        raise _forbidden("Editors can only view their own approval requests.")

    return jsonable_encoder(_ar_dict(ar, current_user.role))


# ─── POST /api/approvals/{id}/approve ────────────────────────────────────────

@router.post("/{ar_id}/approve")
async def approve_approval(
    ar_id: int,
    body: ApprovalReview,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    ar = await _load_ar(db, ar_id)
    if ar is None:
        raise _not_found()

    if ar.status != "pending":
        raise _conflict(f"Cannot approve a request with status '{ar.status}'.")

    now = datetime.now(timezone.utc)
    ar.status = "approved"
    ar.reviewed_by = current_user.id
    ar.reviewed_at = now
    ar.review_comment = body.review_comment

    env_project_id = ar.environment.project_id

    # Apply the change
    if ar.action == "create":
        config = ConfigEntry(
            environment_id=ar.environment_id,
            key=ar.key,
            value=ar.proposed_value,
            config_type=ar.config_type,
            is_sensitive=(ar.config_type == "secret"),
            version=1,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.add(config)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DUPLICATE_RESOURCE",
                    "message": "A config with this key already exists in this environment.",
                    "field": "key",
                },
            )
        # Link approval to the created config
        ar.config_entry_id = config.id
        await db.flush()

        await create_audit_log(
            db,
            user_id=current_user.id,
            action="config_created",
            resource_type="config",
            resource_id=config.id,
            project_id=env_project_id,
            details={"key": config.key, "environment": ar.environment.name, "config_type": config.config_type, "via_approval": ar_id},
            ip_address=_client_ip(request),
        )

    elif ar.action == "update":
        if ar.config_entry_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Target config no longer exists.", "field": None},
            )
        config = await db.get(ConfigEntry, ar.config_entry_id)
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOT_FOUND", "message": "Target config no longer exists.", "field": None},
            )
        if ar.proposed_value is not None:
            config.value = ar.proposed_value
            config.version += 1
        config.updated_by = current_user.id
        await db.flush()

        await create_audit_log(
            db,
            user_id=current_user.id,
            action="config_updated",
            resource_type="config",
            resource_id=config.id,
            project_id=env_project_id,
            details={"key": config.key, "environment": ar.environment.name, "config_type": config.config_type, "via_approval": ar_id, "version": config.version},
            ip_address=_client_ip(request),
        )

    elif ar.action == "delete":
        if ar.config_entry_id is not None:
            config = await db.get(ConfigEntry, ar.config_entry_id)
            if config is not None:
                await create_audit_log(
                    db,
                    user_id=current_user.id,
                    action="config_deleted",
                    resource_type="config",
                    resource_id=config.id,
                    project_id=env_project_id,
                    details={"key": config.key, "environment": ar.environment.name, "config_type": config.config_type, "via_approval": ar_id},
                    ip_address=_client_ip(request),
                )
                await db.delete(config)
                await db.flush()

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="approval_approved",
        resource_type="approval",
        resource_id=ar.id,
        project_id=env_project_id,
        details={"key": ar.key, "action": ar.action, "environment": ar.environment.name, "comment": body.review_comment},
        ip_address=_client_ip(request),
    )

    await db.flush()
    db.expire(ar)  # force reload of reviewer relationship from DB
    ar = await _load_ar(db, ar_id)
    return jsonable_encoder(_ar_dict(ar, current_user.role))


# ─── POST /api/approvals/{id}/reject ─────────────────────────────────────────

@router.post("/{ar_id}/reject")
async def reject_approval(
    ar_id: int,
    body: ApprovalReview,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    ar = await _load_ar(db, ar_id)
    if ar is None:
        raise _not_found()

    if ar.status != "pending":
        raise _conflict(f"Cannot reject a request with status '{ar.status}'.")

    ar.status = "rejected"
    ar.reviewed_by = current_user.id
    ar.reviewed_at = datetime.now(timezone.utc)
    ar.review_comment = body.review_comment

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="approval_rejected",
        resource_type="approval",
        resource_id=ar.id,
        project_id=ar.environment.project_id,
        details={"key": ar.key, "action": ar.action, "environment": ar.environment.name, "comment": body.review_comment},
        ip_address=_client_ip(request),
    )

    await db.flush()
    db.expire(ar)  # force reload of reviewer relationship from DB
    ar = await _load_ar(db, ar_id)
    return jsonable_encoder(_ar_dict(ar, current_user.role))


# ─── POST /api/approvals/{id}/cancel ─────────────────────────────────────────

@router.post("/{ar_id}/cancel")
async def cancel_approval(
    ar_id: int,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    ar = await _load_ar(db, ar_id)
    if ar is None:
        raise _not_found()

    # Editors can only cancel their own; admin can cancel any
    if current_user.role == "editor" and ar.requested_by != current_user.id:
        raise _forbidden("Editors can only cancel their own approval requests.")

    if ar.status != "pending":
        raise _conflict(f"Cannot cancel a request with status '{ar.status}'.")

    ar.status = "cancelled"

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="approval_cancelled",
        resource_type="approval",
        resource_id=ar.id,
        project_id=ar.environment.project_id,
        details={"key": ar.key, "action": ar.action, "environment": ar.environment.name},
        ip_address=_client_ip(request),
    )

    await db.flush()
    ar = await _load_ar(db, ar_id)
    return jsonable_encoder(_ar_dict(ar, current_user.role))
