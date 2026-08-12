from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.pagination import PageMeta
from app.modules.contracts.models import (
    AwardCriterion,
    CommitteeMember,
    Contract,
    ContractHistoryEntry,
    ContractSource,
    Extension,
    InternalStatus,
    Modification,
    PhaseDocument,
)


class ContractorRef(BaseModel):
    id: int
    name: str
    tax_id: str | None = None


class ContractSummary(BaseModel):
    id: int
    file_code: str
    status: str
    lot: str
    subject: str | None = None
    contract_type: str | None = None
    procedure: str | None = None
    contractor: ContractorRef | None = None
    award_amount: Decimal | None = None
    published_at: datetime | None = None
    start_date: date | None = None
    calculated_end_date: date | None = None
    expiry_warning: bool
    possibly_finished: bool
    internal_status: InternalStatus
    department_ids: list[int] = []

    @classmethod
    def from_contract(cls, contract: Contract) -> "ContractSummary":
        return cls(**_summary_fields(contract))


def _summary_fields(contract: Contract) -> dict[str, Any]:
    contractor = None
    if contract.contractor is not None:
        contractor = ContractorRef(
            id=contract.contractor.id,
            name=contract.contractor.canonical_name,
            tax_id=contract.contractor.tax_id,
        )
    return {
        "id": contract.id,
        "file_code": contract.file_code,
        "status": contract.status,
        "lot": contract.lot,
        "subject": contract.subject,
        "contract_type": contract.contract_type,
        "procedure": contract.procedure,
        "contractor": contractor,
        "award_amount": contract.award_amount,
        "published_at": contract.published_at,
        "start_date": contract.start_date,
        "calculated_end_date": contract.calculated_end_date,
        "expiry_warning": contract.expiry_warning,
        "possibly_finished": contract.possibly_finished,
        "internal_status": contract.internal_status,
        "department_ids": [d.id for d in contract.departments],
    }


class ContractDetail(ContractSummary):
    source: ContractSource
    processing_type: str | None = None
    awarding_body: str | None = None
    awarding_department: str | None = None
    raw_contractor_name: str | None = None
    tender_amount: Decimal | None = None
    award_amount_vat: Decimal | None = None
    estimated_value: Decimal | None = None
    budget_no_vat: Decimal | None = None
    budget_vat: Decimal | None = None
    formalized_at: date | None = None
    end_date: date | None = None
    duration_months: int | None = None
    warning_months_override: int | None = None
    cpv_code: str | None = None
    cpv_description: str | None = None
    nuts_code: str | None = None
    nuts_description: str | None = None
    financing: str | None = None
    links: dict[str, Any] | None = None
    phase_urls: dict[str, Any] | None = None
    received_offers: int | None = None
    is_harmonized: bool | None = None
    allows_extensions: bool | None = None
    allows_modifications: bool | None = None
    social_reserve: bool | None = None
    subcontracting_allowed: bool | None = None
    enriched_at: datetime | None = None
    first_synced_at: datetime | None = None
    last_synced_at: datetime | None = None
    siblings: list[ContractSummary] = []
    counters: dict[str, int]
    created_at: datetime

    @classmethod
    def build(
        cls,
        contract: Contract,
        siblings: list[Contract],
        counters: dict[str, int],
    ) -> "ContractDetail":
        return cls(
            **_summary_fields(contract),
            source=contract.source,
            processing_type=contract.processing_type,
            awarding_body=contract.awarding_body,
            awarding_department=contract.awarding_department,
            raw_contractor_name=contract.raw_contractor_name,
            tender_amount=contract.tender_amount,
            award_amount_vat=contract.award_amount_vat,
            estimated_value=contract.estimated_value,
            budget_no_vat=contract.budget_no_vat,
            budget_vat=contract.budget_vat,
            formalized_at=contract.formalized_at,
            end_date=contract.end_date,
            duration_months=contract.duration_months,
            warning_months_override=contract.warning_months_override,
            cpv_code=contract.cpv_code,
            cpv_description=contract.cpv_description,
            nuts_code=contract.nuts_code,
            nuts_description=contract.nuts_description,
            financing=contract.financing,
            links=contract.links,
            phase_urls=contract.phase_urls,
            received_offers=contract.received_offers,
            is_harmonized=contract.is_harmonized,
            allows_extensions=contract.allows_extensions,
            allows_modifications=contract.allows_modifications,
            social_reserve=contract.social_reserve,
            subcontracting_allowed=contract.subcontracting_allowed,
            enriched_at=contract.enriched_at,
            first_synced_at=contract.first_synced_at,
            last_synced_at=contract.last_synced_at,
            siblings=[ContractSummary.from_contract(s) for s in siblings],
            counters=counters,
            created_at=contract.created_at,
        )


class ContractCreate(BaseModel):
    file_code: str = Field(min_length=1, max_length=100)
    status: str = Field(default="", max_length=100)
    lot: str = Field(default="", max_length=50)
    subject: str = Field(min_length=3)
    contract_type: str | None = None
    procedure: str | None = None
    processing_type: str | None = None
    award_amount: Decimal | None = None
    tender_amount: Decimal | None = None
    formalized_at: date | None = None
    duration_months: int | None = Field(default=None, ge=1)
    cpv_code: str | None = Field(default=None, max_length=255)
    department_ids: list[int] = []


class BulkAssignRequest(BaseModel):
    contract_ids: list[int] = Field(min_length=1, max_length=500)
    department_ids: list[int] = Field(min_length=1, max_length=20)
    mode: Literal["add", "replace"] = "add"


class BulkAssignResult(BaseModel):
    updated: int
    unchanged: int
    missing: list[int]


class ContractUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=3)
    contract_type: str | None = None
    procedure: str | None = None
    processing_type: str | None = None
    internal_status: InternalStatus | None = None
    warning_months_override: int | None = Field(default=None, ge=0)


class HistoryEntryResponse(BaseModel):
    id: int
    field: str
    old_value: str | None = None
    new_value: str | None = None
    user_id: int | None = None
    change_type: str
    changed_at: datetime

    @classmethod
    def from_entry(cls, entry: ContractHistoryEntry) -> "HistoryEntryResponse":
        return cls(
            id=entry.id,
            field=entry.field,
            old_value=entry.old_value,
            new_value=entry.new_value,
            user_id=entry.user_id,
            change_type=entry.change_type.value,
            changed_at=entry.changed_at,
        )


class ExtensionResponse(BaseModel):
    id: int
    number: int
    start_date: date | None = None
    end_date: date | None = None
    amount: Decimal | None = None
    fiscal_year: int | None = None

    @classmethod
    def from_extension(cls, extension: Extension) -> "ExtensionResponse":
        return cls(
            id=extension.id,
            number=extension.number,
            start_date=extension.start_date,
            end_date=extension.end_date,
            amount=extension.amount,
            fiscal_year=extension.fiscal_year,
        )


class ModificationResponse(BaseModel):
    id: int
    number: int
    approved_at: date | None = None
    type: str | None = None
    amount: Decimal | None = None

    @classmethod
    def from_modification(cls, modification: Modification) -> "ModificationResponse":
        return cls(
            id=modification.id,
            number=modification.number,
            approved_at=modification.approved_at,
            type=modification.type,
            amount=modification.amount,
        )


class AwardCriterionResponse(BaseModel):
    id: int
    position: int
    name: str
    weight: Decimal | None = None
    breakdown: dict[str, Any] | None = None

    @classmethod
    def from_criterion(cls, criterion: AwardCriterion) -> "AwardCriterionResponse":
        return cls(
            id=criterion.id,
            position=criterion.position,
            name=criterion.name,
            weight=criterion.weight,
            breakdown=criterion.breakdown,
        )


class CommitteeMemberResponse(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    role: str | None = None

    @classmethod
    def from_member(cls, member: CommitteeMember) -> "CommitteeMemberResponse":
        return cls(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            role=member.role,
        )


class PhaseDocumentResponse(BaseModel):
    """storage_key no s'exposa mai: la còpia local es serveix amb token efímer."""

    id: int
    phase: str
    title: str | None = None
    doc_type: str | None = None
    size: int | None = None
    download_url: str | None = None
    has_copy: bool = False

    @classmethod
    def from_document(cls, document: PhaseDocument) -> "PhaseDocumentResponse":
        return cls(
            id=document.id,
            phase=document.phase.value,
            title=document.title,
            doc_type=document.doc_type,
            size=document.size,
            download_url=document.download_url,
            has_copy=document.storage_key is not None,
        )


class PagedContractsResponse(BaseModel):
    data: list[ContractSummary]
    meta: PageMeta


class PagedHistoryResponse(BaseModel):
    data: list[HistoryEntryResponse]
    meta: PageMeta
