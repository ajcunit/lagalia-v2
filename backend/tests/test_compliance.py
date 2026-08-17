"""Motor de regles LCSP (specs/compliance-rules.md)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.db import session_factory
from app.modules.compliance import engine
from tests.conftest import login_headers

pytestmark = pytest.mark.anyio

TODAY = date(2026, 8, 15)


def test_minor_thresholds_by_type() -> None:
    over = engine.check_minor(
        contract_type="Serveis", award_amount=Decimal("15000.01"),
        duration_years=0, duration_months=6, when=TODAY,
    )
    assert engine.worst_status(over) == "no_conforme"
    works_ok = engine.check_minor(
        contract_type="Obres", award_amount=Decimal("39999.99"),
        duration_years=1, duration_months=0, when=TODAY,
    )
    assert engine.worst_status(works_ok) == "conforme"
    too_long = engine.check_minor(
        contract_type="Serveis", award_amount=Decimal("1000"),
        duration_years=1, duration_months=1, when=TODAY,
    )
    assert engine.worst_status(too_long) == "no_conforme"
    unknown = engine.check_minor(
        contract_type="Serveis", award_amount=None,
        duration_years=None, duration_months=None, when=TODAY,
    )
    assert engine.worst_status(unknown) == "no_verificable"


def test_plan_entry_threshold() -> None:
    warn = engine.check_plan_entry(
        contract_type="Serveis", estimated_amount=Decimal("20000"), fiscal_year=2026
    )
    assert engine.worst_status(warn) == "avis"
    ok = engine.check_plan_entry(
        contract_type="Obres", estimated_amount=Decimal("20000"), fiscal_year=2026
    )
    assert engine.worst_status(ok) == "conforme"


def test_rule_versioning_by_date() -> None:
    assert engine.rule_for("minor.amount", date(2017, 1, 1)) is None
    assert engine.rule_for("minor.amount", date(2020, 1, 1)) is not None


async def test_compliance_api(api_client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin_user = await make_user("admin")
    employee = await make_user("employee")
    admin = login_headers(api_client, admin_user.email)

    # employee sense compliance:run → 403.
    assert (
        api_client.get(
            "/api/v1/compliance/rules", headers=login_headers(api_client, employee.email)
        ).status_code
        == 403
    )
    rules = api_client.get("/api/v1/compliance/rules", headers=admin)
    assert rules.status_code == 200
    assert any(r["rule_id"] == "minor.amount" for r in rules.json()["data"])

    # Entrada de pla sobre llindar → avis + review persistida.
    created = api_client.post(
        "/api/v1/plan",
        json={
            "fiscal_year": 2099, "quarter": 1,
            "subject": "Servei gran de prova compliance", "contract_type": "Serveis",
            "estimated_amount": 20000,
        },
        headers=admin,
    )
    entry_id = created.json()["id"]
    check = api_client.post(
        "/api/v1/compliance/check",
        json={"subject_type": "plan_entry", "subject_id": entry_id},
        headers=admin,
    )
    assert check.status_code == 200, check.text
    assert check.json()["status"] == "avis"

    batch = api_client.post(
        "/api/v1/compliance/check-plan", json={"fiscal_year": 2099}, headers=admin
    )
    assert batch.status_code == 200
    row = next(r for r in batch.json()["data"] if r["entry_id"] == entry_id)
    assert row["status"] == "avis"

    async with session_factory() as session:
        count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM compliance_reviews "
                    "WHERE subject_type = 'plan_entry' AND subject_id = :i"
                ),
                {"i": entry_id},
            )
        ).scalar_one()
    assert count >= 2

    assert (
        api_client.post(
            "/api/v1/compliance/check",
            json={"subject_type": "minor_contract", "subject_id": 999999999},
            headers=admin,
        ).status_code
        == 404
    )
    api_client.delete(f"/api/v1/plan/{entry_id}", headers=admin)

async def test_review_document_endpoint(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, api_client, make_user
) -> None:
    """Revisió legal d'un document del repositori (specs/legal-corpus.md)."""
    from uuid import uuid4

    admin_user = await make_user("admin")
    employee = await make_user("employee")
    dm_other = await make_user("dept_manager")  # departament ≠ el del contracte
    admin = login_headers(api_client, admin_user.email)

    tag = uuid4().hex[:8]
    async with session_factory() as session:
        dept_a = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'RevA') RETURNING id"),
                {"c": f"RA-{tag}"},
            )
        ).scalar_one()
        dept_b = (
            await session.execute(
                text("INSERT INTO departments (code, name) VALUES (:c, 'RevB') RETURNING id"),
                {"c": f"RB-{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO user_departments (user_id, department_id) VALUES (:u, :d)"),
            {"u": dm_other.id, "d": dept_a},
        )
        contract_id = (
            await session.execute(
                text(
                    "INSERT INTO contracts (file_code, status, lot, subject) "
                    "VALUES (:f, 'Formalitzat', '', 'Revisió legal doc') RETURNING id"
                ),
                {"f": f"LEGALDOC/{tag}"},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO contract_departments (contract_id, department_id) VALUES (:c, :d)"),
            {"c": contract_id, "d": dept_b},
        )
        doc_no_copy = (
            await session.execute(
                text(
                    "INSERT INTO phase_documents (contract_id, phase, title) "
                    "VALUES (:c, 'licitacio', 'PPT sense còpia') RETURNING id"
                ),
                {"c": contract_id},
            )
        ).scalar_one()
        doc_with_copy = (
            await session.execute(
                text(
                    "INSERT INTO phase_documents (contract_id, phase, title, storage_key) "
                    "VALUES (:c, 'licitacio', 'PPT amb còpia', 'k-legal') RETURNING id"
                ),
                {"c": contract_id},
            )
        ).scalar_one()
        await session.commit()

    def url(doc_id: int) -> str:
        return f"/api/v1/compliance/documents/{doc_id}/review/stream"

    # Sense compliance:run → 403; inexistent → 404; sense còpia local → 409.
    assert (
        api_client.post(url(doc_with_copy), headers=login_headers(api_client, employee.email))
        .status_code
        == 403
    )
    assert api_client.post(url(999999999), headers=admin).status_code == 404
    assert api_client.post(url(doc_no_copy), headers=admin).status_code == 409

    # Abast departamental també al subrecurs: dept_manager d'un ALTRE
    # departament amb compliance:run → 404 (mai 403 que confirmi l'existència).
    assert (
        api_client.post(url(doc_with_copy), headers=login_headers(api_client, dm_other.email))
        .status_code
        == 404
    )

    # Èxit amb storage i LLM simulats: NDJSON articles → delta → done.
    class DummyStorage:
        async def get(self, key: str) -> bytes:
            assert key == "k-legal"
            return b"pdf-fals"

    monkeypatch.setattr("app.core.storage.get_storage", lambda: DummyStorage())
    monkeypatch.setattr(
        "app.ai.rag.extract_text",
        lambda content: "Plec de clàusules administratives del servei de prova. " * 5,
    )

    async def fake_events(session, document_text, **kwargs):  # type: ignore[no-untyped-def]
        assert "Plec de clàusules" in document_text
        yield {
            "type": "articles",
            "articles": [{"article": "Artículo 118", "norm_title": "LCSP", "url": "u"}],
        }
        yield {"type": "delta", "text": "✅ conforme amb LCSP art. 118"}

    monkeypatch.setattr(
        "app.modules.compliance.router.legal_corpus.review_text_events", fake_events
    )
    response = api_client.post(url(doc_with_copy), headers=admin)
    assert response.status_code == 200, response.text

    import json as _json

    events = [_json.loads(line) for line in response.text.splitlines() if line.strip()]
    kinds = [e["type"] for e in events]
    assert "articles" in kinds and "delta" in kinds and kinds[-1] == "done"

    # Persistència amb rastre: review del subjecte 'document' + auditoria.
    async with session_factory() as session:
        review_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM compliance_reviews "
                    "WHERE subject_type = 'document' AND subject_id = :i"
                ),
                {"i": doc_with_copy},
            )
        ).scalar_one()
        audit_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE action = 'compliance.review_document' AND resource_id = :i"
                ),
                {"i": str(doc_with_copy)},
            )
        ).scalar_one()
        # Neteja (l'esborrat del contracte arrossega phase_documents per CASCADE).
        await session.execute(
            text(
                "DELETE FROM compliance_reviews "
                "WHERE subject_type = 'document' AND subject_id = :i"
            ),
            {"i": doc_with_copy},
        )
        await session.execute(text("DELETE FROM contracts WHERE id = :i"), {"i": contract_id})
        await session.execute(
            text("DELETE FROM departments WHERE id IN (:a, :b)"), {"a": dept_a, "b": dept_b}
        )
        await session.commit()
    assert review_count == 1
    assert audit_count == 1
