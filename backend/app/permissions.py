from fastapi import Depends, HTTPException, status

from app.schemas import UserResponse

# ─── Permission matrix ────────────────────────────────────────────────────────

PERMISSIONS: dict[str, dict[str, list[str]]] = {
    "admin": {
        "users": ["list", "create", "edit_role", "deactivate"],
        "projects": ["list", "create", "edit", "delete", "view"],
        "configs": ["list", "view", "view_secret", "create", "edit", "delete"],
        "configs_production": ["create_direct", "edit_direct", "delete"],
        "approvals": ["list_all", "approve", "reject"],
        "audit": ["view_all", "export"],
    },
    "editor": {
        "users": [],
        "projects": ["list", "create", "edit_own", "view"],
        "configs": ["list", "view", "view_secret", "create", "edit", "delete"],
        "configs_production": ["create_with_approval", "edit_with_approval"],
        "approvals": ["list_own", "create", "cancel_own"],
        "audit": ["view_project"],
    },
    "viewer": {
        "users": [],
        "projects": ["list", "view"],
        "configs": ["list", "view"],
        "configs_production": [],
        "approvals": [],
        "audit": ["view_project"],
    },
}


def has_permission(role: str, resource: str, action: str) -> bool:
    role_perms = PERMISSIONS.get(role, {})
    return action in role_perms.get(resource, [])


# ─── Dependencies ─────────────────────────────────────────────────────────────

def require_permission(resource: str, action: str):
    """
    FastAPI dependency that enforces a permission check.
    Usage: Depends(require_permission("configs", "create"))
    """
    from app.dependencies import get_current_user  # local import avoids circular

    async def _check(current_user: UserResponse = Depends(get_current_user)):
        if not has_permission(current_user.role, resource, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "FORBIDDEN", "message": "You don't have permission to perform this action.", "field": None},
            )
        return current_user

    return _check
