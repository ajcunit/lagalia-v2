"""Favorits (specs/favorites.md). Propietat estricta per usuari: una
carpeta d'un altre usuari és un 404 (mai un 403 que en confirmi
l'existència). El snapshot es desa aquí; `contracts` no es toca mai."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.modules.audit.models import AuditActorType
from app.modules.audit.service import record_audit
from app.modules.favorites.models import Favorite, FavoriteFolder
from app.modules.public_registry.router import get_public_contract
from app.modules.users.dependencies import get_request_context
from app.modules.users.service import RequestContext

router = APIRouter(tags=["favorites"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContextDep = Annotated[RequestContext, Depends(get_request_context)]
UseDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("tools:use"))]

COLORS = {"blue", "green", "amber", "red", "purple", "pink", "teal", "gray"}


class FolderBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = None


class FolderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str | None = None


class FolderResponse(BaseModel):
    id: int
    name: str
    description: str | None
    color: str | None
    favorites_count: int


class AddFavoriteBody(BaseModel):
    file_code: str = Field(min_length=1, max_length=100)


class FavoriteResponse(BaseModel):
    id: int
    file_code: str
    subject: str | None
    awarding_body: str | None
    published_at: datetime | None
    snapshot: list[dict[str, Any]]
    created_at: datetime


def _check_color(color: str | None) -> None:
    if color is not None and color not in COLORS:
        raise Problem(422, "Color desconegut", "validation", detail=", ".join(sorted(COLORS)))


async def _own_folder(session: AsyncSession, folder_id: int, user_id: int) -> FavoriteFolder:
    folder = await session.get(FavoriteFolder, folder_id)
    if folder is None or folder.user_id != user_id:
        raise Problem(404, "Carpeta desconeguda", "not-found")
    return folder


async def _audit(
    session: AsyncSession, user_id: int, action: str, resource: str, ctx: RequestContext
) -> None:
    await record_audit(
        session,
        actor_type=AuditActorType.USER,
        action=action,
        success=True,
        actor_id=user_id,
        resource_type="favorites",
        resource_id=resource,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
        trace_id=ctx.trace_id,
    )


def _folder_response(folder: FavoriteFolder, count: int) -> FolderResponse:
    return FolderResponse(
        id=folder.id,
        name=folder.name,
        description=folder.description,
        color=folder.color,
        favorites_count=count,
    )


@router.get("/folders", operation_id="listFolders")
async def list_folders(session: SessionDep, authz_ctx: UseDep) -> dict[str, list[FolderResponse]]:
    rows = (
        await session.execute(
            select(FavoriteFolder, func.count(Favorite.id))
            .join(Favorite, isouter=True)
            .where(FavoriteFolder.user_id == authz_ctx.user.id)
            .group_by(FavoriteFolder.id)
            .order_by(FavoriteFolder.name)
        )
    ).all()
    return {"data": [_folder_response(folder, count) for folder, count in rows]}


@router.post("/folders", operation_id="createFolder", status_code=201)
async def create_folder(
    body: FolderBody, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep
) -> FolderResponse:
    _check_color(body.color)
    folder = FavoriteFolder(
        user_id=authz_ctx.user.id,
        name=body.name,
        description=body.description,
        color=body.color,
    )
    session.add(folder)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "favorites.folder_created", str(folder.id), ctx)
    await session.commit()
    return _folder_response(folder, 0)


@router.patch("/folders/{id}", operation_id="updateFolder")
async def update_folder(
    id: int, body: FolderPatch, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep
) -> FolderResponse:
    folder = await _own_folder(session, id, authz_ctx.user.id)
    _check_color(body.color)
    if body.name is not None:
        folder.name = body.name
    if body.description is not None:
        folder.description = body.description
    if body.color is not None:
        folder.color = body.color
    count = (
        await session.execute(
            select(func.count()).select_from(Favorite).where(Favorite.folder_id == id)
        )
    ).scalar_one()
    await _audit(session, authz_ctx.user.id, "favorites.folder_updated", str(id), ctx)
    await session.commit()
    return _folder_response(folder, count)


@router.delete("/folders/{id}", operation_id="deleteFolder", status_code=204)
async def delete_folder(id: int, session: SessionDep, authz_ctx: UseDep, ctx: ContextDep) -> None:
    folder = await _own_folder(session, id, authz_ctx.user.id)
    await session.delete(folder)
    await _audit(session, authz_ctx.user.id, "favorites.folder_deleted", str(id), ctx)
    await session.commit()


@router.get("/folders/{id}/favorites", operation_id="listFavorites")
async def list_favorites(
    id: int, session: SessionDep, authz_ctx: UseDep
) -> dict[str, list[FavoriteResponse]]:
    await _own_folder(session, id, authz_ctx.user.id)
    favorites = (
        await session.execute(
            select(Favorite).where(Favorite.folder_id == id).order_by(Favorite.created_at.desc())
        )
    ).scalars()
    return {"data": [FavoriteResponse.model_validate(f, from_attributes=True) for f in favorites]}


@router.post("/folders/{id}/favorites", operation_id="addFavorite", status_code=201)
async def add_favorite(
    id: int,
    body: AddFavoriteBody,
    session: SessionDep,
    authz_ctx: UseDep,
    ctx: ContextDep,
) -> FavoriteResponse:
    await _own_folder(session, id, authz_ctx.user.id)
    existing = (
        await session.execute(
            select(Favorite.id).where(
                Favorite.folder_id == id, Favorite.file_code == body.file_code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Problem(409, "Aquest expedient ja és a la carpeta", "conflict")

    # Snapshot del registre públic (404 si no existeix). MAI s'escriu a contracts.
    detail = await get_public_contract(body.file_code, session, authz_ctx)
    rows: list[dict[str, Any]] = detail["data"]
    first = rows[0]
    published = first.get("published_at")
    if isinstance(published, str):
        published = datetime.fromisoformat(published)
    favorite = Favorite(
        folder_id=id,
        file_code=body.file_code,
        subject=first.get("subject"),
        awarding_body=first.get("awarding_body"),
        published_at=published,
        snapshot=jsonable_encoder(rows),
    )
    session.add(favorite)
    await session.flush()
    await _audit(session, authz_ctx.user.id, "favorites.added", body.file_code, ctx)
    await session.commit()
    return FavoriteResponse.model_validate(favorite, from_attributes=True)


@router.delete(
    "/folders/{id}/favorites/{favorite_id}", operation_id="removeFavorite", status_code=204
)
async def remove_favorite(
    id: int,
    favorite_id: Annotated[int, Path()],
    session: SessionDep,
    authz_ctx: UseDep,
    ctx: ContextDep,
) -> None:
    await _own_folder(session, id, authz_ctx.user.id)
    favorite = await session.get(Favorite, favorite_id)
    if favorite is None or favorite.folder_id != id:
        raise Problem(404, "Favorit desconegut", "not-found")
    await session.delete(favorite)
    await _audit(session, authz_ctx.user.id, "favorites.removed", favorite.file_code, ctx)
    await session.commit()
