"""Referències externes d'un projecte del generador (specs/docgen-external-refs.md).

Documents del SuperBuscador indexats TEMPORALMENT i NOMÉS dins de
l'àmbit del projecte: taula pròpia (project_chunks), mai al corpus
municipal, amb caducitat i purga.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import providers, rag, tasks
from app.core.db import session_factory
from app.core.storage import get_storage
from app.integrations import hub
from app.integrations.pscp.connector import PscpConnector
from app.jobs.registry import JobContext, job

logger = structlog.get_logger()

_EMBED_BATCH = 16


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


@job("docgen.index_external", max_attempts=3, backoff_seconds=60)
async def index_external(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    ref_id = int(payload["project_document_id"])
    async with session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT id, project_id, title, source_url, storage_key "
                    "FROM project_documents WHERE id = :id"
                ),
                {"id": ref_id},
            )
        ).first()
    if row is None:
        return {"status": "missing"}

    async def mark_failed(detail: str) -> None:
        async with session_factory() as failed_session:
            await failed_session.execute(
                text(
                    "UPDATE project_documents SET status = 'failed', error_detail = :d "
                    "WHERE id = :id"
                ),
                {"d": detail[:1000], "id": ref_id},
            )
            await failed_session.commit()

    try:
        if row.storage_key:
            # Pujada local: el fitxer ja és a l'storage, no cal descarregar res.
            storage_key = row.storage_key
            content = await get_storage().get(storage_key)
        else:
            if not row.source_url:
                raise ValueError("referència sense URL d'origen ni fitxer pujat")
            async with session_factory() as session:
                connector = await hub.get_connector(session, "pscp")
                await session.commit()
            if not isinstance(connector, PscpConnector):  # defensa de registre
                raise TypeError("El hub ha resolt un connector inesperat per a 'pscp'")
            async with connector.client() as client:
                content, content_type = await client.download_document(row.source_url)

            import uuid as _uuid

            storage_key = f"projects/{row.project_id}/{_uuid.uuid4().hex}.pdf"
            await get_storage().put(storage_key, content, content_type)

        import asyncio as _asyncio

        extracted = await _asyncio.to_thread(rag.extract_text, content)
        chunks = rag.chunk_text(extracted)
        if not chunks:
            raise ValueError("el PDF no conté text extraïble")

        async with session_factory() as session:
            resolved = await tasks.resolve(session, "rag.embed")
            vectors: list[list[float]] = []
            for start in range(0, len(chunks), _EMBED_BATCH):
                batch = chunks[start : start + _EMBED_BATCH]
                vectors.extend(
                    await providers.embed(resolved.profile, batch, model=resolved.model)
                )
            await session.execute(
                text("DELETE FROM project_chunks WHERE project_document_id = :id"),
                {"id": ref_id},
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                await session.execute(
                    text(
                        "INSERT INTO project_chunks (project_id, project_document_id, "
                        "chunk_index, content, embedding) "
                        "VALUES (:p, :d, :i, :c, CAST(:e AS vector))"
                    ),
                    {
                        "p": row.project_id,
                        "d": ref_id,
                        "i": index,
                        "c": chunk,
                        "e": _vector_literal(vector),
                    },
                )
            await session.execute(
                text(
                    "UPDATE project_documents SET status = 'indexed', storage_key = :k, "
                    "chunks_count = :n, indexed_at = now(), error_detail = NULL "
                    "WHERE id = :id"
                ),
                {"k": storage_key, "n": len(chunks), "id": ref_id},
            )
            await session.commit()
        logger.info("project_ref_indexed", ref_id=ref_id, chunks=len(chunks))
        return {"status": "indexed", "chunks": len(chunks)}
    except Exception as exc:  # l'error queda visible a la UI, mai tomba el worker
        await mark_failed(f"{type(exc).__name__}: {exc}")
        logger.warning("project_ref_failed", ref_id=ref_id, error=str(exc))
        return {"status": "failed", "detail": str(exc)}


@job("docgen.purge_expired")
async def purge_expired(ctx: JobContext) -> dict[str, Any]:
    """Purga diària: índexs temporals caducats + fitxers de l'storage."""
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, storage_key FROM project_documents WHERE expires_at < now()"
                )
            )
        ).all()
        for row in rows:
            if row.storage_key:
                try:
                    storage = get_storage()
                    delete = getattr(storage, "delete", None)
                    if delete is not None:
                        await delete(row.storage_key)
                except Exception as exc:  # noqa: BLE001 — el fitxer orfe no bloqueja la purga
                    logger.warning("purge_storage_failed", key=row.storage_key, error=str(exc))
            await session.execute(
                text("DELETE FROM project_documents WHERE id = :id"), {"id": row.id}
            )
        await session.commit()
    logger.info("project_refs_purged", purged=len(rows))
    return {"purged": len(rows)}


async def search_project_chunks(
    session: AsyncSession, project_id: int, query: str, *, limit: int = 4
) -> list[dict[str, Any]]:
    """Cerca dins dels chunks TEMPORALS del projecte (mai al corpus general)."""
    resolved = await tasks.resolve(session, "rag.embed")
    vectors = await providers.embed(resolved.profile, [query], model=resolved.model)
    rows = (
        await session.execute(
            text(
                "SELECT pc.content, pd.title, pd.file_code, "
                "pc.embedding <=> CAST(:q AS vector) AS distance "
                "FROM project_chunks pc "
                "JOIN project_documents pd ON pd.id = pc.project_document_id "
                "WHERE pc.project_id = :p AND pc.embedding IS NOT NULL "
                "AND pd.status = 'indexed' AND pd.expires_at > now() "
                "ORDER BY distance LIMIT :lim"
            ),
            {"q": _vector_literal(vectors[0]), "p": project_id, "lim": limit},
        )
    ).all()
    return [
        {
            "content": row.content,
            "document_title": row.title,
            "file_code": row.file_code,
            "doc_type": "extern",
            "origin": "extern",
        }
        for row in rows
    ]


def default_expiry() -> datetime:
    from datetime import timedelta

    return datetime.now(UTC) + timedelta(days=30)
