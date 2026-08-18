# Sincronització de contractes (Estat: implementada)

## Context i objectiu

Tercera PR de la Fase 1: el job `sync.contracts` amb el pipeline de referència de [08-hub-integracions.md](../docs/08-hub-integracions.md) §4 i el mapeig de l'annex [A1](../docs/annexos/A1-mapeig-socrata.md) com a especificació camp a camp.

## Comportament

Donat el connector `socrata` activat i el codi INE10 configurat al setup,
Quan s'executa el job `sync.contracts`,
Aleshores els contractes majors de Transparència Catalunya queden a la BD (normalitzats, amb adjudicatari resolt, departaments assignats per regles i historial de canvis), amb el `sync_run` tancat amb comptadors i el progrés observable.

Regles verificables:

- **Mapeig A1 literal** (`socrata/mapping.py`): camps directes i renoms de §1–§2; `status = resultat ‖ fase_publicacio` (primer no buit); `parse_duration` amb les 4 regles de §3 (número directe; regex anys/mesos/dies; `+1 mes` si `dies > 15`; `null` si total 0); dates calculades **només** si hi ha formalització i durada (`start = formalització + 1 dia`, `end = formalització + mesos + 1 dia`); camps url-o-objecte normalitzats sempre a string dins `links`/`phase_urls` (§4–§5); `content_hash` SHA-256 del JSON canònic (v1 era MD5).
- **Resolucions v2 de les ambigüitats marcades a l'A1**:
  - La duplicitat v1 (`import_adjudicacio_sense` també a `import_licitar_sense_iva`) **es descarta**: només `award_amount`. Anotat a l'annex.
  - `awarding_body` i `awarding_department` (destins v2 d'A1 §1) s'afegeixen a `contracts` (migració 0006) i a [04-model-de-dades.md](../docs/04-model-de-dades.md) §2 — les regles d'associació els avaluen.
  - Les variants `*_expedient` dels pressupostos no tenen columna: queden a `raw`.
- **Adjudicataris** (`contractors/service.py`): l'àlies substitueix el nom abans de desar (el nom original va a `raw_contractor_name`); sense àlies, es reutilitza per `tax_id` o es crea; després de cada sync es (re)generen els `contractor_duplicates` per NIF compartit — **sempre**, a diferència de la v1.
- **Regles d'associació** (`contracts/rules.py`): actives per prioritat descendent, la primera que casa assigna; camps avaluables `awarding_department`, `awarding_body`, `subject`, `cpv_code` i imports per a `amount`; **tots els operadors implementats** (`equals`, `contains` i `starts_with` case-insensitive; `gt`/`lt` numèrics) — resol el ⚠️ d'A1 §8.
- **Job `sync.contracts`** (idempotent, `dedup_key`):
  1. crea `sync_run` (`running`, trigger del payload);
  2. client via hub (desactivat → el job falla amb el 409 explicat);
  3. **incremental** per camp d'actualització `>=` inici de l'últim run amb èxit, **només si el connector té `incremental_field` configurat** — verificat contra l'API real (2026-08-12): el dataset `ybgg-dgi6` **no té** `data_actualitzacio` (0 de 1000 registres), així que per defecte el sync és complet, com preveu [08](../docs/08-hub-integracions.md) §2.1 («quan el dataset ho permet»); payload `full: true` força complet igualment; filtre sempre per `codi_ine10` de settings (`org.ine10_code`; si falta → error clar);
  4. per registre: mapa → upsert per (`file_code`, `status`, `lot`); hash igual → `unchanged`; diferent → actualització camp a camp + **una entrada d'historial `sync` per camp canviat**; nou → herència de departaments del mateix expedient, regles d'associació, resolució d'adjudicatari;
  5. errors per registre → `sync_item_logs` i es continua (run `partial`);
  6. progrés a `set_progress` per pàgines; comptadors finals (`new/updated/unchanged/total_source`) i estat `success|partial|failed`.
- Cap crida externa fora del job; TLS verificat; cap SoQL fora del builder.

## Canvis d'API

Cap endpoint nou (el llançament manual per `POST /sync-runs` arriba amb l'API de sync, PR posterior). El job es pot encuar internament i des del scheduler.

## Canvis de dades

Migració `0006_awarding_fields`: `contracts.awarding_body`, `contracts.awarding_department` (indexada, l'avaluen les regles). [04-model-de-dades.md](../docs/04-model-de-dades.md) §2 actualitzat a la mateixa PR.

## Seguretat i permisos

- El job corre com a sistema; les escriptures queden a `contract_history` (`sync`) i el run a `sync_runs` — no s'audita registre a registre a `audit_log` (seria soroll); l'execució i el resultat sí que són observables via job.
- `raw` conserva el registre original per a traçabilitat; no conté dades personals més enllà del NIF d'empresa ja públic.

## UI

Cap (pantalla de sincronitzacions: Fase 2 de la UI; el progrés ja és consumible per SSE).

## Fora d'abast

- Syncs de pròrrogues/modificacions, menors i CPV (PR F1-4).
- `alerts.recompute` complet i `enrich.contract` (PR F1-7); el sync deixa `calculated_end_date` a punt.
- `POST /sync-runs` (API) i programació cron configurable.

### Identitat de fila per id_intern (fix 2026-08-18, cas 4732/2026)

El portal SUBSTITUEIX la fila del dataset quan la fase avança (Adjudicació →
Formalització) mantenint `id_intern` estable per lot. La cerca de la fila
local es fa primer per (file_code, lot, raw id_intern) i només si no hi ha
coincidència per la clau natural (file_code, status, lot): així un canvi de
fase ACTUALITZA la fila (amb el canvi d'estat historiat) en lloc de crear-ne
una de nova i deixar l'anterior òrfena. El duplicat existent (4732/2026) es
va fusionar a mà: fills moguts a la fila original, valors vigents aplicats i
fila sobrera esborrada.

## Criteris d'acceptació

- [x] Mapper: parse_duration (número, text amb anys/mesos/dies, dies>15, zero→null), status fallback, url-o-objecte, dates calculades condicionals, hash estable.
- [x] Regles: tots els operadors + prioritat + primera-que-casa (tests parametritzats).
- [x] Adjudicataris: àlies aplicat, reutilització per NIF, duplicats per NIF detectats a cada sync.
- [x] Sync e2e (MockTransport): alta nova amb departaments per regla; re-sync sense canvis → `unchanged`; canvi d'import → `updated` + historial; registre corrupte → `sync_item_logs` + run `partial`.
- [x] Incremental: el segon run filtra per `data_actualitzacio` del run anterior.
- [x] `ruff`, `mypy --strict` i tota la suite verds.
