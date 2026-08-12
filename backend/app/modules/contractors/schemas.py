from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from app.core.pagination import PageMeta


class ContractorRanking(BaseModel):
    id: int
    name: str
    tax_id: str | None = None
    contracts_count: int
    contracts_amount: Decimal | None = None
    minor_count: int
    minor_amount: Decimal | None = None
    total_amount: Decimal


class ContractorProfile(ContractorRanking):
    nationality: str | None = None
    company_type: str | None = None
    third_sector: bool = False
    phone: str | None = None
    email: str | None = None
    aliases: list[str] = []
    created_at: datetime


class ContractorDuplicateResponse(BaseModel):
    id: int
    status: str
    contractor_1: ContractorRanking
    contractor_2: ContractorRanking
    resolved_by: int | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class DuplicateResolveRequest(BaseModel):
    action: Literal["merge_1", "merge_2", "reject"]
    notes: str | None = None


class PagedRankingResponse(BaseModel):
    data: list[ContractorRanking]
    meta: PageMeta


class PagedDuplicatesResponse(BaseModel):
    data: list[ContractorDuplicateResponse]
    meta: PageMeta


def ranking_from_dict(values: dict[str, Any]) -> ContractorRanking:
    return ContractorRanking(**values)
