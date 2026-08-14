"""Cercador CPV (specs/cpv-search.md): cerca manual i arbre lazy."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.modules.contracts.models import CpvCode, CpvLevel

router = APIRouter(tags=["reference"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UseDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("tools:use"))]


@router.get("/cpv", operation_id="searchCpv")
async def search_cpv(
    session: SessionDep,
    _authz: UseDep,
    query: Annotated[str | None, Query(min_length=2, max_length=200)] = None,
    parent: Annotated[str | None, Query(max_length=20)] = None,
    level: Annotated[CpvLevel | None, Query()] = None,
) -> dict[str, list[dict[str, Any]]]:
    child = CpvCode.__table__.alias("child")
    stmt = select(
        CpvCode.code,
        CpvCode.description,
        CpvCode.level,
        CpvCode.parent_code,
        exists(select(1).where(child.c.parent_code == CpvCode.code)).label("has_children"),
    )
    if query:
        if query[0].isdigit():
            stmt = stmt.where(CpvCode.code.like(query.replace("%", "") + "%"))
        else:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(CpvCode.description.ilike(f"%{escaped}%", escape="\\"))
    elif parent:
        stmt = stmt.where(CpvCode.parent_code == parent)
    else:
        stmt = stmt.where(CpvCode.parent_code.is_(None))
    if level is not None:
        stmt = stmt.where(CpvCode.level == level)
    rows = (await session.execute(stmt.order_by(CpvCode.code).limit(50))).all()
    return {
        "data": [
            {
                "code": r.code,
                "description": r.description,
                "level": r.level.value if r.level else None,
                "parent_code": r.parent_code,
                "has_children": r.has_children,
            }
            for r in rows
        ]
    }
