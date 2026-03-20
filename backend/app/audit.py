import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

logger = logging.getLogger(__name__)


async def create_audit_log(
    db: AsyncSession,
    *,
    user_id: int,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    project_id: int | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Persist an audit log entry.
    Secrets must NEVER appear in `details` — callers are responsible for scrubbing.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        project_id=project_id,
        details=json.dumps(details or {}),
        ip_address=ip_address,
    )
    db.add(entry)
    try:
        await db.flush()  # get the ID without committing the outer transaction
    except Exception as exc:
        logger.error("Failed to write audit log [%s/%s]: %s", action, resource_type, exc)
        raise
    return entry
