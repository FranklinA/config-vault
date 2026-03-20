from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─── Shared mini-schemas ─────────────────────────────────────────────────────

class UserMini(BaseModel):
    id: int
    name: str
    email: str

    model_config = {"from_attributes": True}


class UserTiny(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class ProjectMini(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class EnvironmentMini(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str  # str, not EmailStr — .local domains are valid in dev
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


# ─── User ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str  # str, not EmailStr — .local and internal domains must be allowed
    password: str = Field(..., min_length=8)
    role: str = Field(..., pattern="^(admin|editor|viewer)$")


class UserUpdateRole(BaseModel):
    role: str = Field(..., pattern="^(admin|editor|viewer)$")


class UserUpdateStatus(BaseModel):
    is_active: bool


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Project ──────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class EnvironmentResponse(BaseModel):
    id: int
    name: str
    require_approval: bool
    config_count: int = 0

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    owner: UserMini
    environments: list[EnvironmentResponse] = []
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── ConfigEntry ──────────────────────────────────────────────────────────────

CONFIG_TYPES = {"string", "number", "boolean", "json", "secret", "feature_flag"}


class ConfigEntryCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    value: str
    config_type: str
    description: str | None = None

    @field_validator("config_type")
    @classmethod
    def validate_config_type(cls, v: str) -> str:
        if v not in CONFIG_TYPES:
            raise ValueError(f"config_type must be one of: {', '.join(sorted(CONFIG_TYPES))}")
        return v


class ConfigEntryUpdate(BaseModel):
    value: str | None = None
    description: str | None = None


class ConfigEntryResponse(BaseModel):
    id: int
    key: str
    value: str  # may be "********" for secrets viewed by viewer
    config_type: str
    description: str | None
    is_sensitive: bool
    version: int
    created_by: UserTiny
    updated_by: UserTiny
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── ApprovalRequest ──────────────────────────────────────────────────────────

class ApprovalRequestCreate(BaseModel):
    environment_id: int
    action: str = Field(..., pattern="^(create|update|delete)$")
    key: str = Field(..., min_length=1, max_length=255)
    proposed_value: str | None = None
    config_type: str
    config_entry_id: int | None = None

    @field_validator("config_type")
    @classmethod
    def validate_config_type(cls, v: str) -> str:
        if v not in CONFIG_TYPES:
            raise ValueError(f"config_type must be one of: {', '.join(sorted(CONFIG_TYPES))}")
        return v


class ApprovalReview(BaseModel):
    review_comment: str | None = None


class ApprovalRequestResponse(BaseModel):
    id: int
    config_entry_id: int | None
    environment: EnvironmentMini
    project: ProjectMini
    action: str
    key: str
    proposed_value: str | None  # "********" for secrets viewed by viewer
    config_type: str
    current_value: str | None
    status: str
    requested_by: UserTiny
    reviewed_by: UserTiny | None
    review_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


# ─── AuditLog ─────────────────────────────────────────────────────────────────

class AuditLogResponse(BaseModel):
    id: int
    user: UserTiny
    action: str
    resource_type: str
    resource_id: int | None
    project: ProjectMini | None
    details: Any  # parsed JSON
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Error ────────────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    detail: ErrorDetail


# ─── Pagination ───────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    pages: int


# Update forward refs
TokenResponse.model_rebuild()
