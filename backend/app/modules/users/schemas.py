from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr

from app.modules.users.models import User, UserRole


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
            # El DNI viu xifrat; es desxifra i s'exposa amb el CRUD d'usuaris.
            dni=None,
            can_audit=user.can_audit,
            can_plan=user.can_plan,
            auth_source="local" if user.password_hash else "ldap",
            departments=[
                DepartmentRef(id=d.id, code=d.code, name=d.name) for d in user.departments
            ],
            created_at=user.created_at,
        )
