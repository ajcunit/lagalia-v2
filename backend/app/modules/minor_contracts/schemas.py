from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.core.pagination import PageMeta
from app.modules.contracts.models import InternalStatus
from app.modules.contracts.schemas import ContractorRef
from app.modules.minor_contracts.models import MinorContract


class MinorContractResponse(BaseModel):
    id: int
    file_code: str
    contract_type: str | None = None
    description: str | None = None
    contractor: ContractorRef | None = None
    award_amount: Decimal | None = None
    award_date: date | None = None
    fiscal_year: int | None = None
    duration_years: int | None = None
    duration_months: int | None = None
    duration_days: int | None = None
    settlement_type: str | None = None
    settlement_date: date | None = None
    settlement_amount: Decimal | None = None
    internal_status: InternalStatus
    department_ids: list[int] = []
    last_synced_at: datetime | None = None

    @classmethod
    def from_minor(cls, minor: MinorContract) -> "MinorContractResponse":
        contractor = None
        if minor.contractor is not None:
            contractor = ContractorRef(
                id=minor.contractor.id,
                name=minor.contractor.canonical_name,
                tax_id=minor.contractor.tax_id,
            )
        return cls(
            id=minor.id,
            file_code=minor.file_code,
            contract_type=minor.contract_type,
            description=minor.description,
            contractor=contractor,
            award_amount=minor.award_amount,
            award_date=minor.award_date,
            fiscal_year=minor.fiscal_year,
            duration_years=minor.duration_years,
            duration_months=minor.duration_months,
            duration_days=minor.duration_days,
            settlement_type=minor.settlement_type,
            settlement_date=minor.settlement_date,
            settlement_amount=minor.settlement_amount,
            internal_status=minor.internal_status,
            department_ids=[d.id for d in minor.departments],
            last_synced_at=minor.last_synced_at,
        )


class MinorContractUpdate(BaseModel):
    internal_status: InternalStatus | None = None
    department_ids: list[int] | None = None


class PagedMinorsResponse(BaseModel):
    data: list[MinorContractResponse]
    meta: PageMeta
