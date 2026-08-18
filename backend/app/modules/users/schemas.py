from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core import crypto
from app.core.pagination import PageMeta
from app.core.passwords import password_policy_errors
from app.modules.users.models import User, UserRole


def _validate_password(password: str) -> str:
    if errors := password_policy_errors(password):
        raise ValueError("contrasenya no vàlida: " + "; ".join(errors))
    return password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 — no és cap secret
    expires_in: int


class DepartmentRef(BaseModel):
    id: int
    code: str
    name: str


class PermissionScope(BaseModel):
    type: Literal["all", "departments"]
    department_ids: list[int] | None = None


class MyPermissionsResponse(BaseModel):
    role: UserRole
    actions: list[str]
    scope: PermissionScope
    can_switch_view: bool
    # Mòduls desactivats des de la configuració: el frontend n'amaga les
    # entrades de menú (specs/module-flags.md).
    disabled_modules: list[str] = []


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    active: bool
    dni: str | None = None
    can_audit: bool
    can_plan: bool
    auth_source: Literal["local", "ldap"]
    departments: list[DepartmentRef]
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            active=user.active,
            dni=crypto.decrypt_value(user.dni_encrypted) if user.dni_encrypted else None,
            can_audit=user.can_audit,
            can_plan=user.can_plan,
            auth_source="local" if user.password_hash else "ldap",
            departments=[
                DepartmentRef(id=d.id, code=d.code, name=d.name) for d in user.departments
            ],
            created_at=user.created_at,
        )


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    role: UserRole
    # Absent = usuari de directori (LDAP); mai es guarda en clar.
    password: str | None = None
    department_ids: list[int] = []
    can_audit: bool = False
    can_plan: bool = False

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str | None) -> str | None:
        return _validate_password(value) if value is not None else None


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    role: UserRole | None = None
    active: bool | None = None
    password: str | None = None
    department_ids: list[int] | None = None
    can_audit: bool | None = None
    can_plan: bool | None = None

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str | None) -> str | None:
        return _validate_password(value) if value is not None else None


class MeUpdate(BaseModel):
    """PATCH /me: només nom, DNI i contrasenya (mai rol ni correu)."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    dni: str | None = Field(default=None, min_length=8, max_length=20)
    password: str | None = None

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str | None) -> str | None:
        return _validate_password(value) if value is not None else None


class PagedUsersResponse(BaseModel):
    data: list[UserResponse]
    meta: PageMeta
