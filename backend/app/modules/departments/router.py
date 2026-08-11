"""Endpoints de departaments. Prims: la lògica és al servei."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Authorize, AuthzContext
from app.core.db import get_session
from app.core.pagination import PageMeta
from app.modules.departments import repository, service
from app.modules.departments.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    PagedDepartmentsResponse,
)
from app.modules.users import repository as users_repository
from app.modules.users.dependencies import get_request_context
from app.modules.users.schemas import UserResponse
from app.modules.users.service import RequestContext

router = APIRouter(tags=["departments"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
ResourceId = Annotated[int, Path(ge=1)]


@router.get("/departments", operation_id="listDepartments")
async def list_departments(
    session: SessionDep,
    _authz: Annotated[AuthzContext, Depends(Authorize("departments:read"))],
    page_size: Annotated[int, Query(alias="page[size]", ge=1, le=500)] = 50,
    page_cursor: Annotated[str | None, Query(alias="page[cursor]")] = None,
    active: Annotated[bool | None, Query(alias="filter[active]")] = None,
) -> PagedDepartmentsResponse:
    departments, total, next_cursor = await repository.list_departments(
        session, active=active, page_size=page_size, cursor=page_cursor
    )
    return PagedDepartmentsResponse(
        data=[DepartmentResponse.from_department(d) for d in departments],
        meta=PageMeta(total=total, next_cursor=next_cursor),
    )


@router.post("/departments", operation_id="createDepartment", status_code=201)
async def create_department(
    body: DepartmentCreate,
    session: SessionDep,
    authz: Annotated[AuthzContext, Depends(Authorize("departments:write"))],
    ctx: ContextDep,
) -> DepartmentResponse:
    department = await service.create_department(session, body, authz.user, ctx)
    return DepartmentResponse.from_department(department)


@router.get("/departments/{id}", operation_id="getDepartment")
async def get_department(
    id: ResourceId,
    session: SessionDep,
    _authz: Annotated[AuthzContext, Depends(Authorize("departments:read"))],
) -> DepartmentResponse:
    return DepartmentResponse.from_department(await service.get_department(session, id))


@router.patch("/departments/{id}", operation_id="updateDepartment")
async def update_department(
    id: ResourceId,
    body: DepartmentUpdate,
    session: SessionDep,
    authz: Annotated[AuthzContext, Depends(Authorize("departments:write"))],
    ctx: ContextDep,
) -> DepartmentResponse:
    department = await service.update_department(session, id, body, authz.user, ctx)
    return DepartmentResponse.from_department(department)


@router.delete("/departments/{id}", operation_id="deactivateDepartment", status_code=204)
async def deactivate_department(
    id: ResourceId,
    session: SessionDep,
    authz: Annotated[AuthzContext, Depends(Authorize("departments:write"))],
    ctx: ContextDep,
) -> None:
    await service.deactivate_department(session, id, authz.user, ctx)


@router.get("/departments/{id}/users", operation_id="listDepartmentUsers")
async def list_department_users(
    id: ResourceId,
    session: SessionDep,
    _authz: Annotated[AuthzContext, Depends(Authorize("users:read"))],
) -> dict[str, list[UserResponse]]:
    await service.get_department(session, id)  # 404 si no existeix
    users = await users_repository.list_department_users(session, id)
    return {"data": [UserResponse.from_user(u) for u in users]}
