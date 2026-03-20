import json as json_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import create_audit_log
from app.dependencies import get_current_user, get_db, require_role
from app.encryption import decrypt, encrypt
from app.models import ApprovalRequest, ConfigEntry, Environment
from app.schemas import (
    ConfigEntryCreate,
    ConfigEntryResponse,
    ConfigEntryUpdate,
    UserResponse,
    UserTiny,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/environments/{env_id}/configs",
    tags=["configs"],
)

MASKED = "********"


# ─── Value validation ─────────────────────────────────────────────────────────

def _validate_value(config_type: str, value: str) -> None:
    if config_type == "number":
        try:
            float(value)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_CONFIG_VALUE", "message": "Value must be a valid number.", "field": "value"},
            )
    elif config_type in ("boolean", "feature_flag"):
        if value not in ("true", "false"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_CONFIG_VALUE", "message": 'Value must be "true" or "false".', "field": "value"},
            )
    elif config_type == "json":
        try:
            json_mod.loads(value)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_CONFIG_VALUE", "message": "Value must be valid JSON.", "field": "value"},
            )


# ─── Load helpers ─────────────────────────────────────────────────────────────

async def _get_env(
    project_id: int,
    env_id: int,
    db: AsyncSession,
) -> Environment:
    result = await db.execute(
        select(Environment)
        .where(Environment.id == env_id, Environment.project_id == project_id)
        .options(selectinload(Environment.project))
    )
    env = result.scalar_one_or_none()
    if env is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Environment not found.", "field": None},
        )
    return env


async def _get_config(
    db: AsyncSession,
    config_id: int,
    env_id: int,
) -> ConfigEntry:
    result = await db.execute(
        select(ConfigEntry)
        .where(ConfigEntry.id == config_id, ConfigEntry.environment_id == env_id)
        .options(selectinload(ConfigEntry.creator), selectinload(ConfigEntry.updater))
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Config not found.", "field": None},
        )
    return config


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ─── Response builders ────────────────────────────────────────────────────────

def _expose_value(config: ConfigEntry, role: str) -> str:
    """Return the value appropriate for the given role."""
    if not config.is_sensitive:
        return config.value
    if role == "viewer":
        return MASKED
    try:
        return decrypt(config.value)
    except Exception:
        return MASKED


def _config_response(config: ConfigEntry, role: str) -> ConfigEntryResponse:
    return ConfigEntryResponse(
        id=config.id,
        key=config.key,
        value=_expose_value(config, role),
        config_type=config.config_type,
        description=config.description,
        is_sensitive=config.is_sensitive,
        version=config.version,
        created_by=UserTiny(id=config.creator.id, name=config.creator.name),
        updated_by=UserTiny(id=config.updater.id, name=config.updater.name),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _approval_dict(ar: ApprovalRequest, role: str) -> dict:
    """Build serialisable dict for ApprovalRequestResponse."""
    proposed = ar.proposed_value
    if ar.config_type == "secret" and proposed is not None:
        if role == "viewer":
            proposed = MASKED
        else:
            try:
                proposed = decrypt(proposed)
            except Exception:
                proposed = MASKED

    current = ar.current_value
    if ar.config_type == "secret" and current is not None:
        if role == "viewer":
            current = MASKED
        else:
            try:
                current = decrypt(current)
            except Exception:
                current = MASKED

    env = ar.environment
    project = env.project

    return {
        "id": ar.id,
        "config_entry_id": ar.config_entry_id,
        "environment": {"id": env.id, "name": env.name},
        "project": {"id": project.id, "name": project.name},
        "action": ar.action,
        "key": ar.key,
        "proposed_value": proposed,
        "config_type": ar.config_type,
        "current_value": current,
        "status": ar.status,
        "requested_by": {"id": ar.requester.id, "name": ar.requester.name},
        "reviewed_by": {"id": ar.reviewer.id, "name": ar.reviewer.name} if ar.reviewer else None,
        "review_comment": ar.review_comment,
        "created_at": ar.created_at,
        "reviewed_at": ar.reviewed_at,
    }


async def _load_approval(db: AsyncSession, ar_id: int) -> ApprovalRequest:
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.id == ar_id)
        .options(
            selectinload(ApprovalRequest.environment).selectinload(Environment.project),
            selectinload(ApprovalRequest.requester),
            selectinload(ApprovalRequest.reviewer),
        )
    )
    return result.scalar_one()


async def _approval_202(ar: ApprovalRequest, db: AsyncSession, role: str) -> JSONResponse:
    ar = await _load_approval(db, ar.id)
    return JSONResponse(
        status_code=202,
        content=jsonable_encoder({
            "message": "Approval request created",
            "approval_request": _approval_dict(ar, role),
        }),
    )


# ─── GET /configs ─────────────────────────────────────────────────────────────

@router.get("")
async def list_configs(
    project_id: int,
    env_id: int,
    config_type: str | None = Query(None),
    search: str | None = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_env(project_id, env_id, db)  # validates ownership

    query = (
        select(ConfigEntry)
        .where(ConfigEntry.environment_id == env_id)
        .options(selectinload(ConfigEntry.creator), selectinload(ConfigEntry.updater))
    )
    if config_type:
        query = query.where(ConfigEntry.config_type == config_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            ConfigEntry.key.ilike(pattern) | ConfigEntry.description.ilike(pattern)
        )

    result = await db.execute(query.order_by(ConfigEntry.key))
    configs = result.scalars().all()
    return [_config_response(c, current_user.role) for c in configs]


# ─── POST /configs ────────────────────────────────────────────────────────────

@router.post("")
async def create_config(
    project_id: int,
    env_id: int,
    body: ConfigEntryCreate,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    env = await _get_env(project_id, env_id, db)

    _validate_value(body.config_type, body.value)

    store_value = encrypt(body.value) if body.config_type == "secret" else body.value
    is_sensitive = body.config_type == "secret"

    # Editor + require_approval → create ApprovalRequest instead
    if env.require_approval and current_user.role == "editor":
        ar = ApprovalRequest(
            config_entry_id=None,
            environment_id=env_id,
            action="create",
            key=body.key,
            proposed_value=store_value,
            config_type=body.config_type,
            current_value=None,
            status="pending",
            requested_by=current_user.id,
        )
        db.add(ar)
        await db.flush()

        await create_audit_log(
            db,
            user_id=current_user.id,
            action="approval_requested",
            resource_type="approval",
            resource_id=ar.id,
            project_id=env.project_id,
            details={
                "action": "create",
                "key": body.key,
                "environment": env.name,
                "config_type": body.config_type,
            },
            ip_address=_client_ip(request),
        )
        return await _approval_202(ar, db, current_user.role)

    # Direct creation (admin, or non-approval environment)
    config = ConfigEntry(
        environment_id=env_id,
        key=body.key,
        value=store_value,
        config_type=body.config_type,
        description=body.description,
        is_sensitive=is_sensitive,
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
            detail={"code": "DUPLICATE_RESOURCE", "message": "A config with this key already exists in this environment.", "field": "key"},
        )

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="config_created",
        resource_type="config",
        resource_id=config.id,
        project_id=env.project_id,
        details=_audit_details_create(config, env.name),
        ip_address=_client_ip(request),
    )

    await db.refresh(config)
    # Reload with relationships
    config = await _get_config(db, config.id, env_id)
    return JSONResponse(
        status_code=201,
        content=jsonable_encoder(_config_response(config, current_user.role)),
    )


# ─── PUT /configs/{config_id} ─────────────────────────────────────────────────

@router.put("/{config_id}")
async def update_config(
    project_id: int,
    env_id: int,
    config_id: int,
    body: ConfigEntryUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    env = await _get_env(project_id, env_id, db)
    config = await _get_config(db, config_id, env_id)

    new_value = body.value
    if new_value is not None:
        _validate_value(config.config_type, new_value)

    if env.require_approval and current_user.role == "editor":
        store_proposed = None
        store_current = None
        if new_value is not None:
            store_proposed = encrypt(new_value) if config.is_sensitive else new_value
            store_current = config.value  # already encrypted if secret

        ar = ApprovalRequest(
            config_entry_id=config.id,
            environment_id=env_id,
            action="update",
            key=config.key,
            proposed_value=store_proposed,
            config_type=config.config_type,
            current_value=store_current,
            status="pending",
            requested_by=current_user.id,
        )
        db.add(ar)
        await db.flush()

        await create_audit_log(
            db,
            user_id=current_user.id,
            action="approval_requested",
            resource_type="approval",
            resource_id=ar.id,
            project_id=env.project_id,
            details={
                "action": "update",
                "key": config.key,
                "environment": env.name,
                "config_type": config.config_type,
            },
            ip_address=_client_ip(request),
        )
        return await _approval_202(ar, db, current_user.role)

    # Direct update
    if new_value is not None:
        config.value = encrypt(new_value) if config.is_sensitive else new_value
        config.version += 1

    if body.description is not None:
        config.description = body.description

    config.updated_by = current_user.id

    await db.flush()

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="config_updated",
        resource_type="config",
        resource_id=config.id,
        project_id=env.project_id,
        details=_audit_details_update(config, env.name),
        ip_address=_client_ip(request),
    )

    config = await _get_config(db, config_id, env_id)
    return _config_response(config, current_user.role)


# ─── DELETE /configs/{config_id} ─────────────────────────────────────────────

@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    project_id: int,
    env_id: int,
    config_id: int,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    env = await _get_env(project_id, env_id, db)
    config = await _get_config(db, config_id, env_id)

    # Editors cannot delete from production
    if current_user.role == "editor" and env.require_approval:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Editors cannot delete configs from production environments.", "field": None},
        )

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="config_deleted",
        resource_type="config",
        resource_id=config.id,
        project_id=env.project_id,
        details={"key": config.key, "environment": env.name, "config_type": config.config_type},
        ip_address=_client_ip(request),
    )

    await db.delete(config)


# ─── POST /configs/{config_id}/reveal ────────────────────────────────────────

@router.post("/{config_id}/reveal")
async def reveal_secret(
    project_id: int,
    env_id: int,
    config_id: int,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    env = await _get_env(project_id, env_id, db)
    config = await _get_config(db, config_id, env_id)

    if not config.is_sensitive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CONFIG_VALUE", "message": "This config is not a secret.", "field": None},
        )

    try:
        plaintext = decrypt(config.value)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DECRYPTION_ERROR", "message": "Could not decrypt secret value.", "field": None},
        )

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="secret_accessed",
        resource_type="config",
        resource_id=config.id,
        project_id=env.project_id,
        details={"key": config.key, "environment": env.name, "note": "value not logged for security"},
        ip_address=_client_ip(request),
    )

    return {"value": plaintext}


# ─── PUT /configs/{config_id}/toggle ─────────────────────────────────────────

@router.put("/{config_id}/toggle")
async def toggle_feature_flag(
    project_id: int,
    env_id: int,
    config_id: int,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    env = await _get_env(project_id, env_id, db)
    config = await _get_config(db, config_id, env_id)

    if config.config_type != "feature_flag":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_CONFIG_VALUE", "message": "Toggle only works on feature_flag configs.", "field": None},
        )

    new_value = "false" if config.value == "true" else "true"

    if env.require_approval and current_user.role == "editor":
        ar = ApprovalRequest(
            config_entry_id=config.id,
            environment_id=env_id,
            action="update",
            key=config.key,
            proposed_value=new_value,
            config_type=config.config_type,
            current_value=config.value,
            status="pending",
            requested_by=current_user.id,
        )
        db.add(ar)
        await db.flush()

        await create_audit_log(
            db,
            user_id=current_user.id,
            action="approval_requested",
            resource_type="approval",
            resource_id=ar.id,
            project_id=env.project_id,
            details={"action": "toggle", "key": config.key, "environment": env.name},
            ip_address=_client_ip(request),
        )
        return await _approval_202(ar, db, current_user.role)

    config.value = new_value
    config.version += 1
    config.updated_by = current_user.id
    await db.flush()

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="config_updated",
        resource_type="config",
        resource_id=config.id,
        project_id=env.project_id,
        details={"key": config.key, "environment": env.name, "old_value": config.value, "new_value": new_value},
        ip_address=_client_ip(request),
    )

    config = await _get_config(db, config_id, env_id)
    return _config_response(config, current_user.role)


# ─── Audit detail helpers ─────────────────────────────────────────────────────

def _audit_details_create(config: ConfigEntry, env_name: str) -> dict:
    if config.is_sensitive:
        return {"key": config.key, "environment": env_name, "config_type": config.config_type, "note": "value not logged for security"}
    return {"key": config.key, "environment": env_name, "config_type": config.config_type, "value": config.value}


def _audit_details_update(config: ConfigEntry, env_name: str) -> dict:
    if config.is_sensitive:
        return {"key": config.key, "environment": env_name, "config_type": config.config_type, "note": "value changed (not logged for security)", "version": config.version}
    return {"key": config.key, "environment": env_name, "config_type": config.config_type, "version": config.version}
