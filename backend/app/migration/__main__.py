"""CLI de la migració v1→v2: python -m app.migration --source-dsn … [--dry-run]."""

import argparse
import asyncio
import sys
from urllib.parse import urlsplit

from app.migration.migrate import run_migration
from app.migration.report import write_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migració de dades v1→v2 (LAGALia)")
    parser.add_argument(
        "--source-dsn",
        required=True,
        help="DSN postgres de la còpia de la v1 (postgresql+asyncpg://…). Només lectura.",
    )
    parser.add_argument("--schema", default="public", help="Esquema d'origen (defecte public)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Calcula i informa sense escriure res"
    )
    parser.add_argument(
        "--report", default="migration-report", help="Directori de l'informe (JSON + MD)"
    )
    args = parser.parse_args()

    results = asyncio.run(run_migration(args.source_dsn, schema=args.schema, dry_run=args.dry_run))
    # El DSN no s'escriu mai a l'informe: només l'amfitrió.
    results["source_host"] = urlsplit(args.source_dsn.replace("+asyncpg", "")).hostname
    report_path = write_report(results, args.report)
    print(f"Informe: {report_path}")

    orphan_count = sum(len(data["orphans"]) for data in results.get("entities", {}).values())
    if orphan_count:
        print(f"Atenció: {orphan_count} entrades òrfenes (vegeu l'informe).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
