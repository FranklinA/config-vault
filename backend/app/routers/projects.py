import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import create_audit_log
from app.dependencies import get_current_user, get_db, require_role
from app.models import ConfigEntry, Environment, Project
from app.schemas import (
    EnvironmentResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    UserMini,
    UserResponse,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "project"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _load_project(db: AsyncSession, project_id: int) -> Project | None:
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.owner), selectinload(Project.environments))
    )
    return result.scalar_one_or_none()


async def _config_counts(db: AsyncSession, env_ids: list[int]) -> dict[int, int]:
    if not env_ids:
        return {}
    result = await db.execute(
        select(ConfigEntry.environment_id, func.count(ConfigEntry.id))
        .where(ConfigEntry.environment_id.in_(env_ids))
        .group_by(ConfigEntry.environment_id)
    )
    return dict(result.all())


async def _build_response(project: Project, db: AsyncSession) -> ProjectResponse:
    env_ids = [e.id for e in project.environments]
    counts = await _config_counts(db, env_ids)
    envs = [
        EnvironmentResponse(
            id=e.id,
            name=e.name,
            require_approval=e.require_approval,
            config_count=counts.get(e.id, 0),
        )
        for e in project.environments
    ]
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        owner=UserMini(
            id=project.owner.id,
            name=project.owner.name,
            email=project.owner.email,
        ),
        environments=envs,
        is_archived=project.is_archived,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# ─── POST /api/projects ───────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin", "editor")),
    db: AsyncSession = Depends(get_db),
):
    slug = _slugify(body.name)

    # Uniqueness check (name and slug)
    existing = await db.execute(
        select(Project).where(
            (Project.name == body.name) | (Project.slug == slug)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "DUPLICATE_RESOURCE",
                "message": "A project with this name already exists.",
                "field": "name",
            },
        )

    project = Project(
        name=body.name,
        slug=slug,
        description=body.description,
        owner_id=current_user.id,
        is_archived=False,
    )
    db.add(project)
    await db.flush()  # get project.id

    # Auto-create 3 fixed environments
    for env_name, require_approval in [
        ("development", False),
        ("staging", False),
        ("production", True),
    ]:
        db.add(
            Environment(
                project_id=project.id,
                name=env_name,
                require_approval=require_approval,
            )
        )

    await db.flush()

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="project_created",
        resource_type="project",
        resource_id=project.id,
        project_id=project.id,
        details={"name": project.name, "slug": project.slug},
        ip_address=_client_ip(request),
    )

    # Reload with relationships
    project = await _load_project(db, project.id)
    return await _build_response(project, db)


# ─── GET /api/projects ────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def list_projects(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    is_archived: bool | None = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Project).options(
        selectinload(Project.owner), selectinload(Project.environments)
    )

    if search:
        pattern = f"%{search}%"
        query = query.where(Project.name.ilike(pattern))
    if is_archived is not None:
        query = query.where(Project.is_archived == is_archived)

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar_one()

    query = (
        query.order_by(Project.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    projects = result.scalars().all()

    data = [await _build_response(p, db) for p in projects]

    return {
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": max(1, -(-total // per_page)),
        },
    }


# ─── GET /api/projects/{id} ───────────────────────────────────────────────────

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Project not found.", "field": None},
        )
    return await _build_response(project, db)


# ─── PUT /api/projects/{id} ───────────────────────────────────────────────────

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role not in ("admin", "editor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "You don't have permission to edit projects.", "field": None},
        )

    project = await _load_project(db, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Project not found.", "field": None},
        )

    # Editors can only edit their own projects
    if current_user.role == "editor" and project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Editors can only edit their own projects.", "field": None},
        )

    changes: dict = {}

    if body.name is not None and body.name != project.name:
        new_slug = _slugify(body.name)
        # Check new name/slug uniqueness (exclude self)
        existing = await db.execute(
            select(Project).where(
                ((Project.name == body.name) | (Project.slug == new_slug))
                & (Project.id != project_id)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "DUPLICATE_RESOURCE",
                    "message": "A project with this name already exists.",
                    "field": "name",
                },
            )
        changes["name"] = {"old": project.name, "new": body.name}
        changes["slug"] = {"old": project.slug, "new": new_slug}
        project.name = body.name
        project.slug = new_slug

    if body.description is not None and body.description != project.description:
        changes["description"] = {"old": project.description, "new": body.description}
        project.description = body.description

    if body.is_archived is not None and body.is_archived != project.is_archived:
        changes["is_archived"] = {"old": project.is_archived, "new": body.is_archived}
        project.is_archived = body.is_archived

    if changes:
        await create_audit_log(
            db,
            user_id=current_user.id,
            action="project_updated",
            resource_type="project",
            resource_id=project.id,
            project_id=project.id,
            details={"changes": changes},
            ip_address=_client_ip(request),
        )

    await db.flush()
    project = await _load_project(db, project_id)
    return await _build_response(project, db)


# ─── DELETE /api/projects/{id} ────────────────────────────────────────────────

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    request: Request,
    current_user: UserResponse = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Project not found.", "field": None},
        )

    await create_audit_log(
        db,
        user_id=current_user.id,
        action="project_deleted",
        resource_type="project",
        resource_id=project.id,
        project_id=project.id,
        details={"name": project.name, "slug": project.slug},
        ip_address=_client_ip(request),
    )

    await db.delete(project)
