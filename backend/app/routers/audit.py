"""
Audit log endpoints (Fase 5).

  GET /api/audit                      — Admin only, full log with filters + pagination
  GET /api/audit/export               — Admin only, CSV download
  GET /api/projects/{id}/audit        — Admin (all), Editor (if owner), Viewer (allowed)
"""
import csv
import io
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import get_current_user, get_db, require_role
from app.models import AuditLog, Project, User
from app.schemas import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(s: str | None, field: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DATE", "message": f"Invalid ISO date: {s}", "field": field},
        )


def _parse_details(raw: str) -> dict:
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _log_dict(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "user": {"id": log.user.id, "name": log.user.name},
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "project": {"id": log.project.id, "name": log.project.name} if log.project else None,
        "details": _parse_details(log.details),
        "ip_address": log.ip_address,
        "created_at": log.created_at,
    }


def _build_query(
    *,
    action: str | None,
    resource_type: str | None,
    user_id: int | None,
    project_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
):
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    if user_id is not None:
        q = q.where(AuditLog.user_id == user_id)
    if project_id is not None:
        q = q.where(AuditLog.project_id == project_id)
    if date_from:
        q = q.where(AuditLog.created_at >= date_from)
    if date_to:
        q = q.where(AuditLog.created_at <= date_to)
    return q


# ─── GET /api/audit ───────────────────────────────────────────────────────────

@router.get("/api/audit")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    user_id: int | None = Query(None),
    project_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    dt_from = _parse_date(date_from, "date_from")
    dt_to = _parse_date(date_to, "date_to")

    base = _build_query(
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        project_id=project_id,
        date_from=dt_from,
        date_to=dt_to,
    )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    data_q = (
        base.options(
            selectinload(AuditLog.user),
            selectinload(AuditLog.project),
        )
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(data_q)).scalars().all()

    return {
        "data": [_log_dict(r) for r in rows],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, -(-total // per_page)),
        },
    }


# ─── GET /api/audit/export ────────────────────────────────────────────────────

@router.get("/api/audit/export")
async def export_audit_logs(
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    user_id: int | None = Query(None),
    project_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    dt_from = _parse_date(date_from, "date_from")
    dt_to = _parse_date(date_to, "date_to")

    base = _build_query(
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        project_id=project_id,
        date_from=dt_from,
        date_to=dt_to,
    )
    data_q = base.options(
        selectinload(AuditLog.user),
        selectinload(AuditLog.project),
    ).order_by(AuditLog.created_at.asc())

    rows = (await db.execute(data_q)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_NONNUMERIC)
    writer.writerow(["timestamp", "user", "action", "resource_type", "resource_id", "project", "details"])
    for log in rows:
        writer.writerow([
            log.created_at.isoformat(),
            log.user.name,
            log.action,
            log.resource_type,
            log.resource_id if log.resource_id is not None else "",
            log.project.name if log.project else "",
            log.details,
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )


# ─── GET /api/projects/{project_id}/audit ────────────────────────────────────

@router.get("/api/projects/{project_id}/audit")
async def list_project_audit_logs(
    project_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify project exists
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Project not found.", "field": None},
        )

    # Editor: only if owner
    if current_user.role == "editor" and project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Editors can only view audit logs for their own projects.", "field": None},
        )

    base = _build_query(
        action=action,
        resource_type=resource_type,
        user_id=None,
        project_id=project_id,
        date_from=None,
        date_to=None,
    )

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    data_q = (
        base.options(
            selectinload(AuditLog.user),
            selectinload(AuditLog.project),
        )
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(data_q)).scalars().all()

    return {
        "data": [_log_dict(r) for r in rows],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, -(-total // per_page)),
        },
    }
