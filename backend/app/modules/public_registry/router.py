"""SuperBuscador: registre públic de tot Catalunya (specs/super-search.md).

Proxy interactiu de només lectura sobre el dataset obert i el portal de
contractació (desviació controlada documentada a la spec): tot filtre
passa pel query builder SoQL i el proxy de fase només accepta URLs del
host del connector pscp.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import authz
from app.core.db import get_session
from app.core.problems import Problem
from app.integrations import hub
from app.integrations.base import ConnectorError
from app.integrations.pscp.connector import PscpConnector
from app.integrations.pscp.extract import collect_committee, collect_criteria, collect_documents
from app.integrations.socrata.connector import SocrataConnector
from app.integrations.socrata.mapping import contractor_fields, map_contract
from app.integrations.socrata.query import SoqlQuery, SoqlValidationError

router = APIRouter(tags=["public-registry"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
UseDep = Annotated[authz.AuthzContext, Depends(authz.Authorize("tools:use"))]


class PublicContractCard(BaseModel):
    file_code: str
    lot: str
    subject: str | None
    awarding_body: str | None
    awarding_department: str | None
    contract_type: str | None
    procedure: str | None
    status: str
    published_at: datetime | None
    budget_vat: Decimal | None
    award_amount: Decimal | None
    contractor_name: str | None
    contractor_nif: str | None
    phase_urls: dict[str, str] | None
    links: dict[str, str] | None


class SearchResponse(BaseModel):
    data: list[PublicContractCard]
    meta: dict[str, Any]


class PhaseDocument(BaseModel):
    source_doc_id: str
    title: str
    doc_type: str
    size: int | None
    download_url: str


class PhaseResponse(BaseModel):
    documents: list[PhaseDocument]
    committee: list[dict[str, str | None]]
    criteria: list[dict[str, Any]]


def _card(record: dict[str, Any]) -> PublicContractCard:
    mapped = map_contract(record)
    contractor = contractor_fields(record)
    return PublicContractCard(
        file_code=mapped["file_code"],
        lot=mapped["lot"],
        subject=mapped["subject"],
        awarding_body=mapped["awarding_body"],
        awarding_department=mapped["awarding_department"],
        contract_type=mapped["contract_type"],
        procedure=mapped["procedure"],
        status=mapped["status"],
        published_at=mapped["published_at"],
        budget_vat=mapped["budget_vat"],
        award_amount=mapped["award_amount"],
        contractor_name=contractor.get("name"),
        contractor_nif=contractor.get("nif"),
        phase_urls=mapped["phase_urls"],
        links=mapped["links"],
    )


async def _socrata(session: AsyncSession) -> SocrataConnector:
    try:
        connector = await hub.get_connector(session, "socrata")
    finally:
        await session.commit()
    if not isinstance(connector, SocrataConnector):  # defensa de registre
        raise TypeError("El hub ha resolt un connector inesperat per a 'socrata'")
    return connector


@router.get("/public-registry/search", operation_id="searchPublicRegistry")
async def search_public_registry(
    session: SessionDep,
    _authz: UseDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    organisme: Annotated[str | None, Query(alias="filter[organisme]", max_length=200)] = None,
    contract_type: Annotated[
        str | None, Query(alias="filter[contract_type]", max_length=100)
    ] = None,
    amount_min: Annotated[Decimal | None, Query(alias="filter[amount_min]", ge=0)] = None,
    amount_max: Annotated[Decimal | None, Query(alias="filter[amount_max]", ge=0)] = None,
    published_from: Annotated[datetime | None, Query(alias="filter[from]")] = None,
    published_to: Annotated[datetime | None, Query(alias="filter[to]")] = None,
    page: Annotated[int, Query(ge=1, le=200)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResponse:
    connector = await _socrata(session)
    try:
        query = SoqlQuery(connector.config["dataset_contracts"])
        if q:
            query = query.full_text(q)
        if organisme:
            query = query.where_contains("nom_organ", organisme)
        if contract_type:
            query = query.where_eq("tipus_contracte", contract_type)
        if amount_min is not None:
            query = query.where_gte_number("pressupost_licitacio_amb", amount_min)
        if amount_max is not None:
            query = query.where_lte_number("pressupost_licitacio_amb", amount_max)
        if published_from is not None:
            query = query.where_gte_timestamp(
                "data_publicacio_anunci", published_from.replace(tzinfo=None)
            )
        if published_to is not None:
            query = query.where_lte_timestamp(
                "data_publicacio_anunci", published_to.replace(tzinfo=None)
            )
        query = (
            query.order_by("data_publicacio_anunci", descending=True)
            .limit(page_size + 1)
            .offset((page - 1) * page_size)
        )
    except SoqlValidationError as exc:
        raise Problem(422, "Filtre de cerca invàlid", "validation", detail=str(exc)) from None

    try:
        async with connector.client() as client:
            records = await client.fetch_page(query)
    except ConnectorError as exc:
        raise Problem(502, "El registre públic no respon", "upstream", detail=str(exc)) from None

    has_more = len(records) > page_size
    return SearchResponse(
        data=[_card(r) for r in records[:page_size]],
        meta={"page": page, "page_size": page_size, "has_more": has_more},
    )


@router.get("/public-registry/contracts/{file_code}", operation_id="getPublicContract")
async def get_public_contract(
    file_code: Annotated[str, Path(min_length=1, max_length=100)],
    session: SessionDep,
    _authz: UseDep,
) -> dict[str, Any]:
    connector = await _socrata(session)
    query = (
        SoqlQuery(connector.config["dataset_contracts"])
        .where_eq("codi_expedient", file_code)
        .order_by("numero_lot")
        .limit(50)
    )
    try:
        async with connector.client() as client:
            records = await client.fetch_page(query)
    except ConnectorError as exc:
        raise Problem(502, "El registre públic no respon", "upstream", detail=str(exc)) from None
    if not records:
        raise Problem(404, "Expedient desconegut al registre públic", "not-found")

    rows = []
    for record in records:
        mapped = map_contract(record)
        mapped.pop("raw", None)
        mapped.pop("content_hash", None)
        mapped["contractor"] = contractor_fields(record)
        rows.append(mapped)
    return {"data": rows}


@router.get("/public-registry/phase", operation_id="getPublicPhase")
async def get_public_phase(
    url: Annotated[str, Query(min_length=10, max_length=1000)],
    session: SessionDep,
    _authz: UseDep,
) -> PhaseResponse:
    try:
        connector = await hub.get_connector(session, "pscp")
    finally:
        await session.commit()
    if not isinstance(connector, PscpConnector):  # defensa de registre
        raise TypeError("El hub ha resolt un connector inesperat per a 'pscp'")

    try:
        async with connector.client() as client:
            payload = await client.fetch_phase(url)
    except ConnectorError as exc:
        # Inclou l'anti-SSRF (host fora del domini) i errors del portal.
        message = str(exc)
        if "fora del domini" in message:
            raise Problem(422, "URL de fase invàlida", "validation", detail=message) from None
        raise Problem(502, "El portal de contractació no respon", "upstream") from None

    base_url = str(connector.config["base_url"]).rstrip("/")
    return PhaseResponse(
        documents=[PhaseDocument(**d) for d in collect_documents(payload, base_url)],
        committee=collect_committee(payload),
        criteria=collect_criteria(payload),
    )
