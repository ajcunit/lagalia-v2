"""B-011: normalització de noms, consolidació i grups de duplicats per NIF."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import session_factory
from app.modules.contractors.normalize import normalize_name
from app.modules.contractors.service import (
    consolidate_same_identity,
    detect_tax_id_duplicates,
    resolve_contractor,
)
from tests.conftest import login_headers


def test_normalize_name_real_patterns() -> None:
    # Variants reals de la BD: puntuació, majúscules i formes societàries.
    assert normalize_name("SOREA, S.A.U.") == normalize_name("Sorea SAU")
    assert normalize_name("EMPRESA MIG S.L.") == normalize_name("EMPRESA MIG SL")
    assert normalize_name("Construccions Puig, S.L.U.") == normalize_name("CONSTRUCCIONS PUIG SLU")
    assert normalize_name("Gestió d'Aigües, S.C.C.L.") == normalize_name("GESTIO D AIGUES SCCL")
    # Noms genuïnament diferents NO col·lideixen.
    assert normalize_name("Serveis del Nord SL") != normalize_name("Serveis del Sud SL")
    # La forma societària només cau del final.
    assert normalize_name("SA de Neteges") == "sa de neteges"
    assert normalize_name(None) == ""


@pytest.fixture
async def nif_world() -> AsyncIterator[dict[str, Any]]:
    tag = uuid4().hex[:8]
    nif = f"B{tag[:7].upper()}0"
    async with session_factory() as session:
        canonical = (
            await session.execute(
                text(
                    "INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t) RETURNING id"
                ),
                {"n": f"NETEGES NORM {tag} S.L.", "t": nif},
            )
        ).scalar_one()
        await session.commit()

    yield {"tag": tag, "nif": nif, "canonical": canonical}

    async with session_factory() as session:
        await session.execute(
            text(
                "DELETE FROM contractor_aliases WHERE contractor_id IN "
                "(SELECT id FROM contractors WHERE tax_id = :t)"
            ),
            {"t": nif},
        )
        await session.execute(
            text(
                "DELETE FROM contractor_duplicates WHERE contractor_id_1 IN "
                "(SELECT id FROM contractors WHERE tax_id = :t) OR contractor_id_2 IN "
                "(SELECT id FROM contractors WHERE tax_id = :t)"
            ),
            {"t": nif},
        )
        await session.execute(text("DELETE FROM contractors WHERE tax_id = :t"), {"t": nif})
        await session.commit()


async def test_trivial_variant_becomes_alias(nif_world: dict[str, Any]) -> None:
    tag, nif = nif_world["tag"], nif_world["nif"]
    async with session_factory() as session:
        # Variant trivial: mateix nom sense punts → àlies, no contractor nou.
        resolved = await resolve_contractor(session, name=f"NETEGES NORM {tag} SL", tax_id=nif)
        assert resolved is not None
        assert resolved.contractor_id == nif_world["canonical"]

        # Nom genuïnament diferent → contractor propi.
        other = await resolve_contractor(session, name=f"ALTRA COSA {tag} SL", tax_id=nif)
        assert other is not None
        assert other.contractor_id != nif_world["canonical"]
        await session.commit()

    async with session_factory() as session:
        aliases = (
            await session.execute(
                text("SELECT alias FROM contractor_aliases WHERE contractor_id = :c"),
                {"c": nif_world["canonical"]},
            )
        ).scalars()
        assert f"NETEGES NORM {tag} SL" in set(aliases)
        count = (
            await session.execute(
                text("SELECT count(*) FROM contractors WHERE tax_id = :t"), {"t": nif}
            )
        ).scalar_one()
        assert count == 2  # canònic + el genuïnament diferent


async def test_consolidate_merges_trivial_variants(nif_world: dict[str, Any]) -> None:
    tag, nif = nif_world["tag"], nif_world["nif"]
    async with session_factory() as session:
        # Dues variants trivials i una de genuïna creades "a la manera antiga".
        for name in (f"NETEGES NORM {tag} SL", f"neteges norm {tag}, s.l."):
            await session.execute(
                text("INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t)"),
                {"n": name, "t": nif},
            )
        await session.execute(
            text("INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t)"),
            {"n": f"DIFERENT DE VERITAT {tag} SA", "t": nif},
        )
        await detect_tax_id_duplicates(session)
        await session.commit()

    async with session_factory() as session:
        result = await consolidate_same_identity(session)
        await session.commit()
    assert result["merged"] >= 2

    async with session_factory() as session:
        remaining = (
            await session.execute(
                text("SELECT canonical_name FROM contractors WHERE tax_id = :t ORDER BY id"),
                {"t": nif},
            )
        ).scalars()
        names = list(remaining)
        assert len(names) == 2  # les 3 variants trivials fusionades en 1 + la genuïna
        pending = (
            await session.execute(
                text(
                    "SELECT count(*) FROM contractor_duplicates d "
                    "JOIN contractors c1 ON c1.id = d.contractor_id_1 "
                    "WHERE d.status = 'pending' AND c1.tax_id = :t"
                ),
                {"t": nif},
            )
        ).scalar_one()
        assert pending == 1  # només el parell genuí

    # Idempotent.
    async with session_factory() as session:
        rerun = await consolidate_same_identity(session)
        await session.commit()
    assert rerun["merged"] == 0


async def test_group_listing_and_bulk_merge(  # type: ignore[no-untyped-def]
    api_client: TestClient, make_user, nif_world: dict[str, Any]
) -> None:
    tag, nif = nif_world["tag"], nif_world["nif"]
    admin = await make_user("admin")
    headers = login_headers(api_client, admin.email)

    async with session_factory() as session:
        for name in (f"VARIANT U {tag} SL", f"VARIANT DOS {tag} SL"):
            await session.execute(
                text("INSERT INTO contractors (canonical_name, tax_id) VALUES (:n, :t)"),
                {"n": name, "t": nif},
            )
        await detect_tax_id_duplicates(session)
        await session.commit()

    groups = api_client.get(
        "/api/v1/contractors/duplicates/groups", params={"q": nif}, headers=headers
    )
    assert groups.status_code == 200, groups.text
    group = next((g for g in groups.json()["data"] if g["tax_id"] == nif), None)
    assert group is not None
    assert len(group["contractors"]) == 3

    # Fusió en bloc al canònic.
    resolved = api_client.post(
        "/api/v1/contractors/duplicates/groups/resolve",
        json={"tax_id": nif, "action": "merge", "canonical_id": nif_world["canonical"]},
        headers=headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["merged"] == 2

    async with session_factory() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM contractors WHERE tax_id = :t"), {"t": nif}
            )
        ).scalar_one()
        assert count == 1
        pending = (
            await session.execute(
                text(
                    "SELECT count(*) FROM contractor_duplicates d "
                    "JOIN contractors c1 ON c1.id = d.contractor_id_1 "
                    "WHERE d.status = 'pending' AND c1.tax_id = :t"
                ),
                {"t": nif},
            )
        ).scalar_one()
        assert pending == 0

    # canonical_id fora del grup → 422.
    invalid = api_client.post(
        "/api/v1/contractors/duplicates/groups/resolve",
        json={"tax_id": nif, "action": "merge", "canonical_id": 99999999},
        headers=headers,
    )
    assert invalid.status_code in (200, 422)  # grup d'un sol membre: no-op vàlid

    # L'històric sobreviu a la fusió: parells «merged» amb instantània
    # encara que els perdedors ja no existeixin (FK SET NULL + snapshot).
    async with session_factory() as session:
        survivors = (
            await session.execute(
                text(
                    "SELECT status, snapshot_1 IS NOT NULL AS s1, "
                    "snapshot_2 IS NOT NULL AS s2 FROM contractor_duplicates "
                    "WHERE snapshot_1->>'tax_id' = :t OR snapshot_2->>'tax_id' = :t"
                ),
                {"t": nif},
            )
        ).all()
    assert len(survivors) >= 1
    assert all(row.status == "merged" and row.s1 and row.s2 for row in survivors)

    # I la pestanya «Fusionats» els mostra, reconstruïts de la instantània.
    merged_list = api_client.get(
        "/api/v1/contractors/duplicates",
        params={"status": "merged", "page[size]": 100},
        headers=headers,
    )
    assert merged_list.status_code == 200, merged_list.text
    names = {
        c["name"]
        for pair in merged_list.json()["data"]
        for c in (pair["contractor_1"], pair["contractor_2"])
    }
    assert any(tag in name for name in names)
