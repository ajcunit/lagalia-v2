"""Job export.contracts (specs/contracts-exports.md).

L'abast efectiu es fixa a l'encuament i viatja al payload: el job no
re-avalua permisos. CSV amb `;` i BOM (paritat v1); XLSX amb openpyxl.
"""

import csv
import io
from typing import Any

import structlog

from app.core.authz import ScopeInfo
from app.core.db import session_factory
from app.core.storage import get_storage
from app.jobs.registry import JobContext, job
from app.modules.contracts import repository
from app.modules.contracts.models import Contract

logger = structlog.get_logger()

CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

HEADERS = [
    "Expedient",
    "Lot",
    "Estat",
    "Estat intern",
    "Objecte",
    "Tipus",
    "Procediment",
    "Adjudicatari",
    "NIF",
    "Import adjudicació",
    "Import licitació",
    "Publicat",
    "Inici",
    "Fi",
    "Fi calculada",
    "Departaments",
    "Alerta fi propera",
    "Possiblement finalitzat",
]


def _row(contract: Contract) -> list[Any]:
    return [
        contract.file_code,
        contract.lot or "",
        contract.status,
        contract.internal_status.value,
        contract.subject or "",
        contract.contract_type or "",
        contract.procedure or "",
        contract.contractor.canonical_name if contract.contractor else "",
        contract.contractor.tax_id if contract.contractor else "",
        contract.award_amount if contract.award_amount is not None else "",
        contract.tender_amount if contract.tender_amount is not None else "",
        contract.published_at.date().isoformat() if contract.published_at else "",
        contract.start_date.isoformat() if contract.start_date else "",
        contract.end_date.isoformat() if contract.end_date else "",
        contract.calculated_end_date.isoformat() if contract.calculated_end_date else "",
        ", ".join(sorted(d.name for d in contract.departments)),
        "Sí" if contract.expiry_warning else "No",
        "Sí" if contract.possibly_finished else "No",
    ]


def _to_csv(rows: list[list[Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(HEADERS)
    writer.writerows(rows)
    # BOM perquè Excel detecti UTF-8 (paritat v1).
    return buffer.getvalue().encode("utf-8-sig")


def _to_xlsx(rows: list[list[Any]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Contractes"
    sheet.append(HEADERS)
    sheet.freeze_panes = "A2"
    for row in rows:
        sheet.append([str(v) if v is not None else "" for v in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@job("export.contracts")
async def export_contracts(ctx: JobContext) -> dict[str, Any]:
    payload = ctx.payload or {}
    fmt = payload.get("format", "csv")
    if fmt not in ("csv", "xlsx"):
        raise ValueError(f"format d'export desconegut: {fmt!r}")
    scope_data = payload.get("scope") or {"type": "all"}
    scope = ScopeInfo(type=scope_data["type"], department_ids=scope_data.get("department_ids"))
    user_id = int(payload["user_id"])
    filters: dict[str, Any] = payload.get("filters") or {}

    rows: list[list[Any]] = []
    async with session_factory() as session:
        async for batch in repository.iter_for_export(
            session, scope=scope, user_id=user_id, filters=filters
        ):
            rows.extend(_row(contract) for contract in batch)
            await ctx.set_progress(min(95, len(rows) // 100), f"{len(rows)} files")

    content = _to_csv(rows) if fmt == "csv" else _to_xlsx(rows)
    content_type = CSV_CONTENT_TYPE if fmt == "csv" else XLSX_CONTENT_TYPE
    storage_key = f"exports/{ctx.job_id}.{fmt}"
    filename = f"contractes-{str(ctx.job_id)[:8]}.{fmt}"
    await get_storage().put(storage_key, content, content_type)

    result = {
        "storage_key": storage_key,
        "filename": filename,
        "rows": len(rows),
        "format": fmt,
        "content_type": content_type,
    }
    logger.info("export_contracts_finished", **result)
    return result
