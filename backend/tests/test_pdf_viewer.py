"""Visor de PDF intern (specs/pdf-viewer.md)."""

import uuid as uuid_module

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.core.storage import get_storage
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio

PDF_BYTES = b"%PDF-1.7 contingut sintetic de prova"
NOT_PDF_BYTES = b"<html>una cosa que NO es un PDF</html>"


@pytest.fixture
async def viewer_world(make_user):  # type: ignore[no-untyped-def]
    tag = uuid_module.uuid4().hex[:8]
    employee_in = await make_user("employee")
    employee_out = await make_user("employee")

    storage = get_storage()
    pdf_key = f"tests/{tag}/doc.pdf"
    html_key = f"tests/{tag}/doc.html"
    await storage.put(pdf_key, PDF_BYTES, "application/pdf")
    await storage.put(html_key, NOT_PDF_BYTES, "text/html")

    async with session_factory() as session:
        dept = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'Visor') RETURNING id"),
                {"c": f"PV-{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
            {"u": employee_in.id, "d": dept},
        )
        contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, published_at) "
                    "VALUES (:f, 'Formalitzat', '', :s, '2026-01-01') RETURNING id"
                ),
                {"f": f"PDF-{tag}/1", "s": f"Servei {tag} amb documents"},
            )
        ).scalar_one()
        other_contract = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject, published_at) "
                    "VALUES (:f, 'Formalitzat', '', :s, '2026-01-01') RETURNING id"
                ),
                {"f": f"PDF-{tag}/2", "s": f"Obra {tag} aliena"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": contract, "d": dept},
        )

        def _doc(cid: int, key: str | None) -> dict:  # type: ignore[type-arg]
            return {"c": cid, "k": key}

        pdf_doc = (
            await session.execute(
                text(
                    "INSERT INTO phase_documents (contract_id, phase, title, storage_key) "
                    "VALUES (:c, 'licitacio', 'Plec de proves.pdf', :k) RETURNING id"
                ),
                _doc(contract, pdf_key),
            )
        ).scalar_one()
        html_doc = (
            await session.execute(
                text(
                    "INSERT INTO phase_documents (contract_id, phase, title, storage_key) "
                    "VALUES (:c, 'licitacio', 'sospitos.html', :k) RETURNING id"
                ),
                _doc(contract, html_key),
            )
        ).scalar_one()
        no_copy_doc = (
            await session.execute(
                text(
                    "INSERT INTO phase_documents (contract_id, phase, title, storage_key) "
                    "VALUES (:c, 'licitacio', 'sense copia', NULL) RETURNING id"
                ),
                {"c": contract},
            )
        ).scalar_one()
        await session.commit()

    yield {
        "tag": tag,
        "employee_in": employee_in,
        "employee_out": employee_out,
        "contract": contract,
        "other_contract": other_contract,
        "pdf_doc": pdf_doc,
        "html_doc": html_doc,
        "no_copy_doc": no_copy_doc,
    }

    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM contracts WHERE file_code LIKE :p"), {"p": f"PDF-{tag}%"}
        )
        await session.execute(text("DELETE FROM departments WHERE code = :c"), {"c": f"PV-{tag}"})
        await session.commit()


def _url(contract_id: int, document_id: int) -> str:
    return f"/api/v1/contracts/{contract_id}/documents/{document_id}/content"


async def test_pdf_served_inline_and_audited(api_client, viewer_world) -> None:  # type: ignore[no-untyped-def]
    w = viewer_world
    headers = login_headers(api_client, w["employee_in"].email)

    response = api_client.get(_url(w["contract"], w["pdf_doc"]), headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-disposition"].startswith("inline")
    assert response.headers["cache-control"] == "no-store"
    assert response.content == PDF_BYTES

    async with session_factory() as session:
        audited = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_log WHERE action = 'contracts.document_view' "
                    "AND resource_id = :r AND actor_id = :a"
                ),
                {"r": str(w["pdf_doc"]), "a": w["employee_in"].id},
            )
        ).scalar_one()
    assert audited >= 1


async def test_non_pdf_never_served_inline(api_client, viewer_world) -> None:  # type: ignore[no-untyped-def]
    w = viewer_world
    headers = login_headers(api_client, w["employee_in"].email)

    response = api_client.get(_url(w["contract"], w["html_doc"]), headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/octet-stream")
    assert response.headers["content-disposition"].startswith("attachment")


async def test_missing_copy_and_wrong_contract(api_client, viewer_world) -> None:  # type: ignore[no-untyped-def]
    w = viewer_world
    headers = login_headers(api_client, w["employee_in"].email)

    assert api_client.get(_url(w["contract"], w["no_copy_doc"]), headers=headers).status_code == 409
    # Document real però penjat d'un ALTRE contracte: mai es serveix.
    out_of_scope = api_client.get(_url(w["other_contract"], w["pdf_doc"]), headers=headers)
    assert out_of_scope.status_code == 404


async def test_departmental_scope_applies_to_content(api_client, viewer_world) -> None:  # type: ignore[no-untyped-def]
    w = viewer_world
    headers = login_headers(api_client, w["employee_out"].email)
    # Fora d'abast: 404 (no es revela l'existència), com la resta de subrecursos.
    response = api_client.get(_url(w["contract"], w["pdf_doc"]), headers=headers)
    assert response.status_code == 404
