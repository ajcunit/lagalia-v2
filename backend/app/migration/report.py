"""Informe de reconciliació de la migració (JSON + Markdown)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_report(results: dict[str, Any], directory: str | Path) -> Path:
    output = Path(directory)
    output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = "-dry-run" if results.get("dry_run") else ""

    json_path = output / f"migration-{stamp}{suffix}.json"
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    lines = [
        f"# Informe de reconciliació v1→v2 — {stamp}",
        "",
        f"Mode: {'**dry-run** (cap escriptura)' if results.get('dry_run') else 'execució real'}",
        "",
        "| Entitat | Llegits | Creats | Actualitzats | Iguals | Òrfenes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for entity, data in results.get("entities", {}).items():
        lines.append(
            f"| {entity} | {data['read']} | {data['created']} | {data['updated']} "
            f"| {data['unchanged']} | {len(data['orphans'])} |"
        )
    checksums = results.get("checksums", {})
    lines += [
        "",
        "## Sumes de control (contractes conciliats)",
        "",
        f"- Conciliats per clau natural: **{checksums.get('matched_contracts', 0)}**",
        f"- ∑ import adjudicació v1: {checksums.get('award_amount_v1', '0')}",
        f"- ∑ import adjudicació v2: {checksums.get('award_amount_v2', '0')}",
        "",
        "## Òrfenes",
        "",
    ]
    any_orphan = False
    for entity, data in results.get("entities", {}).items():
        for orphan in data["orphans"]:
            lines.append(f"- `{entity}`: {orphan}")
            any_orphan = True
    if not any_orphan:
        lines.append("Cap.")
    lines += ["", "## Pendent (fora d'abast de la versió 1 del script)", ""]
    lines += [f"- {item}" for item in results.get("pending", [])]
    lines.append("")

    md_path = output / f"migration-{stamp}{suffix}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path
