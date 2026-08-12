# Model de dades del nucli de contractació (Estat: implementada)

## Context i objectiu

Primera PR de la Fase 1 ([09-roadmap.md](../docs/09-roadmap.md)): materialitza [04-model-de-dades.md](../docs/04-model-de-dades.md) §2 (nucli), §4 (sincronització) i §5 (referència CPV) com a models SQLAlchemy i migració Alembic. És el fonament dels connectors, els syncs i les APIs de contractes de les PRs següents.

## Comportament

Donada la base de dades amb les migracions 0001–0003,
Quan s'executa `alembic upgrade head`,
Aleshores existeixen totes les taules del nucli de contractació amb les seves restriccions, índexs i triggers, de manera reversible.

Regles verificables:

- **Convencions** de la migració 0001: PK identity, `created_at`/`updated_at` amb trigger, FK amb `ON DELETE` explícit, noms anglesos.
- **`contractors`** normalitza adjudicataris (`tax_id` indexat); `contractor_aliases.alias UNIQUE` s'aplica a la ingesta; `contractor_duplicates` amb parell únic i estat.
- **`contracts`**: clau natural v1 **UNIQUE(file_code, status, lot)**; `contractor_id FK` amb `raw_contractor_name` per traçabilitat; imports `NUMERIC(15,2)`; `links`/`phase_urls`/`enrichment`/`raw` JSONB; `content_hash` per a sync incremental; enum `source` i `internal_status`. Índexs: `file_code`, `status`, `contractor_id`, `start_date`, `calculated_end_date`, `cpv_code`, `internal_status`, `source`, **GIN sobre `raw`** i **trigram sobre `subject`**.
- **M2M**: `contract_departments`, `contract_managers`, `minor_contract_departments` (PK composta, `ON DELETE CASCADE`).
- **Satèl·lits**: `extensions` i `modifications` amb `UNIQUE(contract_id, number)`; `award_criteria`, `committee_members`, `phase_documents` (enum `contract_phase`), `contract_history` (enum `change_type`, sense `updated_at`: és un registre, no s'edita).
- **`duplicates`**: parell únic normalitzat (CHECK `contract_id_1 < contract_id_2` + UNIQUE del parell) — el mateix parell no pot entrar dues vegades en cap ordre.
- **`association_rules`**: tots els tipus i operadors declarats com a enums (la v2 els implementa tots).
- **`minor_contracts`**: `file_code UNIQUE`, liquidació i `raw_award`/`raw_settlement`.
- **`sync_runs`** (enums `sync_kind`, `sync_trigger`, `sync_status`) amb comptadors; `sync_item_logs` per registre problemàtic.
- **`cpv_codes`**: `code UNIQUE`, nivell enum, `parent_code`, trigram sobre `description`.
- Models per mòduls d'arquitectura §4: `modules/contracts`, `modules/minor_contracts`, `modules/contractors`; sync a `integrations/`; CPV a `modules/config`? No: `cpv_codes` va a `modules/contracts` (referència de classificació del nucli).

## Canvis d'API

Cap: les APIs arriben amb les PRs següents de la fase (el contracte s'ampliarà llavors).

## Canvis de dades

Migració `0004_contracting_core`: 16 taules noves + 10 enums + índexs (GIN, trigram, únics parcials/composts) + triggers `updated_at`. Reversible.

## Seguretat i permisos

Cap endpoint nou. `phase_documents.download_url` i `storage_key` no contenen mai credencials; el DNI no apareix enlloc del nucli.

## UI

Cap.

## Fora d'abast

- Connectors, jobs de sync i mapeig A1 (PRs 2–4 de la fase).
- APIs i exports (PR 5+).
- Vistes materialitzades del rànquing d'adjudicataris (arriben amb l'API d'adjudicataris).
- Taules d'integracions (`connectors`, `connector_credentials`…): PR 2.

## Criteris d'acceptació

- [x] `alembic upgrade head` i `downgrade 0003` reversibles sobre la BD real.
- [x] Test d'esquema: totes les taules noves existeixen amb els índexs únics clau.
- [x] UNIQUE(file_code, status, lot) i UNIQUE(contract_id, number) verificats amb dades.
- [x] CHECK del parell de duplicats rebutja l'ordre invers i el duplicat.
- [x] Trigram operatiu sobre `contracts.subject` (consulta `%` similarity).
- [x] `ruff`, `mypy --strict` i tota la suite verds.
