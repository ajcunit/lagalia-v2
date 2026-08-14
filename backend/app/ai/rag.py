"""Servei RAG compartit — ingesta i cerca híbrida (specs/rag-service.md).

Pipeline: MinIO → PyMuPDF → chunks (~3.200 chars, solapament, respectant
paràgrafs) → embeddings per lots (tasca rag.embed) → rag_chunks.
Cerca: cosinus pgvector + trigram, fusió per rang.
"""

import asyncio
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import providers, tasks
from app.core.db import session_factory
from app.core.storage import get_storage
from app.jobs.registry import JobContext, job

logger = structlog.get_logger()

CHUNK_SIZE = 3200
CHUNK_OVERLAP = 300
_EMBED_BATCH = 16


def extract_text(content: bytes) -> str:
    """Text pla d'un PDF (PyMuPDF, en thread al job)."""
    import fitz  # pymupdf

    with fitz.open(stream=content, filetype="pdf") as doc:
        return "\n\n".join(page.get_text() for page in doc)


def chunk_text(value: str) -> list[str]:
    """Trossos de ~CHUNK_SIZE chars amb solapament, tallant per paràgraf si es pot."""
    cleaned = "\n".join(line.strip() for line in value.splitlines())
    cleaned = "\n".join(filter(None, cleaned.split("\n\n"))) if cleaned else ""
    text_value = cleaned or value
    chunks: list[str] = []
    start = 0
    while start < len(text_value):
        end = min(start + CHUNK_SIZE, len(text_value))
        if end < len(text_value):
            # Retrocedeix fins a un tall de paràgraf o frase proper.
            for sep in ("\n\n", ". ", "\n"):
                cut = text_value.rfind(sep, start + CHUNK_SIZE // 2, end)
                if cut != -1:
                    end = cut + len(sep)
                    break
        piece = text_value[start:end].strip()
        if len(piece) > 50:  # fragments massa curts no aporten
            chunks.append(piece)
        if end >= len(text_value):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


async def _embed_all(session: AsyncSession, texts: list[str]) -> list[list[float]]:
    resolved = await tasks.resolve(session, "rag.embed")
    vectors: list[list[float]] = []
    for index in range(0, len(texts), _EMBED_BATCH):
        batch = texts[index : index + _EMBED_BATCH]
        vectors.extend(await providers.embed(resolved.profile, batch, model=resolved.model))
    return vectors


async def index_document(session: AsyncSession, document_id: int) -> int:
    """Indexa un document; retorna el nombre de chunks. Idempotent (reemplaça)."""
    row = (
        await session.execute(
            text(
                "SELECT id, contract_id, storage_key FROM phase_documents "
                "WHERE id = :id AND storage_key IS NOT NULL"
            ),
            {"id": document_id},
        )
    ).first()
    if row is None:
        return 0
    content = await get_storage().get(row.storage_key)
    extracted = await asyncio.to_thread(extract_text, content)
    chunks = chunk_text(extracted)
    if not chunks:
        await session.execute(
            text("UPDATE phase_documents SET indexed_at = now() WHERE id = :id"),
            {"id": document_id},
        )
        return 0
    vectors = await _embed_all(session, chunks)
    await session.execute(
        text("DELETE FROM rag_chunks WHERE document_id = :id"), {"id": document_id}
    )
    for index, (piece, vector) in enumerate(zip(chunks, vectors, strict=True)):
        await session.execute(
            text(
                "INSERT INTO rag_chunks (document_id, contract_id, chunk_index, content, "
                "embedding) VALUES (:d, :c, :i, :t, CAST(:e AS vector))"
            ),
            {
                "d": document_id,
                "c": row.contract_id,
                "i": index,
                "t": piece,
                "e": "[" + ",".join(f"{x:.6f}" for x in vector) + "]",
            },
        )
    await session.execute(
        text("UPDATE phase_documents SET indexed_at = now() WHERE id = :id"),
        {"id": document_id},
    )
    return len(chunks)


@job("rag.index")
async def rag_index(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    force = bool(payload.get("force", False))
    limit = int(payload.get("limit") or 500)
    async with session_factory() as session:
        condition = "" if force else "AND indexed_at IS NULL"
        ids = list(
            (
                await session.execute(
                    text(
                        # condition és un literal fix del codi, mai entrada d'usuari.
                        "SELECT id FROM phase_documents "  # noqa: S608
                        f"WHERE storage_key IS NOT NULL {condition} ORDER BY id LIMIT :lim"
                    ),
                    {"lim": limit},
                )
            ).scalars()
        )
    done, chunks_total, failed = 0, 0, 0
    for position, document_id in enumerate(ids, start=1):
        try:
            async with session_factory() as session:
                chunks_total += await index_document(session, document_id)
                await session.commit()
            done += 1
        except Exception as exc:  # un document dolent no atura la ingesta
            failed += 1
            logger.warning("rag_index_document_failed", document_id=document_id, error=str(exc))
        if position % 5 == 0 or position == len(ids):
            suffix = f" ({failed} errors)" if failed else ""
            await ctx.set_progress(
                min(99, (position * 100) // max(1, len(ids))),
                f"{position}/{len(ids)} documents processats{suffix}",
            )
    result = {"documents": done, "chunks": chunks_total, "failed": failed}
    logger.info("rag_index_finished", **result)
    return result


async def search(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 10,
    document_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Cerca híbrida: cosinus + trigram, fusió per posició (RRF simplificat)."""
    resolved = await tasks.resolve(session, "rag.embed")
    vectors = await providers.embed(resolved.profile, [query], model=resolved.model)
    query_vector = "[" + ",".join(f"{x:.6f}" for x in vectors[0]) + "]"

    doc_filter = "AND document_id = ANY(:ids) " if document_ids else ""
    params_extra: dict[str, Any] = {"ids": document_ids} if document_ids else {}
    vector_rows = (
        await session.execute(
            text(
                # doc_filter és un literal fix del codi (mai entrada d'usuari).
                "SELECT id, embedding <=> CAST(:q AS vector) AS distance "  # noqa: S608
                f"FROM rag_chunks WHERE embedding IS NOT NULL {doc_filter}"
                "ORDER BY distance LIMIT :lim"
            ),
            {"q": query_vector, "lim": limit * 2, **params_extra},
        )
    ).all()
    trigram_rows = (
        await session.execute(
            text(
                "SELECT id, similarity(content, :q) AS sim FROM rag_chunks "  # noqa: S608
                f"WHERE (content % :q OR content ILIKE :like) {doc_filter}"
                "ORDER BY sim DESC NULLS LAST LIMIT :lim"
            ),
            {"q": query[:200], "like": f"%{query[:80]}%", "lim": limit * 2, **params_extra},
        )
    ).all()

    scores: dict[int, float] = {}
    for rank, row in enumerate(vector_rows):
        scores[row.id] = scores.get(row.id, 0.0) + 1.0 / (10 + rank)
    for rank, row in enumerate(trigram_rows):
        scores[row.id] = scores.get(row.id, 0.0) + 1.0 / (10 + rank)
    top_ids = [cid for cid, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)][:limit]
    if not top_ids:
        return []

    rows = (
        await session.execute(
            text(
                "SELECT rc.id, rc.content, rc.chunk_index, pd.title, pd.doc_type, pd.phase, "
                "c.file_code, c.id AS contract_id FROM rag_chunks rc "
                "JOIN phase_documents pd ON pd.id = rc.document_id "
                "LEFT JOIN contracts c ON c.id = rc.contract_id "
                "WHERE rc.id = ANY(:ids)"
            ),
            {"ids": top_ids},
        )
    ).all()
    by_id = {row.id: row for row in rows}
    return [
        {
            "chunk_id": row.id,
            "content": row.content,
            "chunk_index": row.chunk_index,
            "document_title": row.title,
            "doc_type": row.doc_type,
            "phase": str(row.phase),
            "file_code": row.file_code,
            "contract_id": row.contract_id,
        }
        for cid in top_ids
        if (row := by_id.get(cid)) is not None
    ]
