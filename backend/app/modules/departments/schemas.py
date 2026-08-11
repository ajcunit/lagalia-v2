from datetime import datetime

from pydantic import BaseModel, Field

from app.core.pagination import PageMeta
from app.modules.departments.models import Department


class GestionaGroup(BaseModel):
    id: str
    name: str | None = None
    href: str | None = None


class DepartmentResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    active: bool
    gestiona_group: GestionaGroup | None = None
    created_at: datetime

    @classmethod
    def from_department(cls, department: Department) -> "DepartmentResponse":
        gestiona_group = None
        if department.gestiona_group_id:
            gestiona_group = GestionaGroup(
                id=department.gestiona_group_id,
                name=department.gestiona_group_name,
                href=department.gestiona_group_href,
            )
        return cls(
            id=department.id,
            code=department.code,
            name=department.name,
            description=department.description,
            active=department.active,
            gestiona_group=gestiona_group,
            created_at=department.created_at,
        )


class DepartmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class DepartmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    active: bool | None = None
    gestiona_group_id: str | None = None


class PagedDepartmentsResponse(BaseModel):
    data: list[DepartmentResponse]
    meta: PageMeta
