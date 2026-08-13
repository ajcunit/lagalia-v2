# Sincronitzacions: historial i llançament manual (Estat: implementada)

## Context i objectiu

Les sincronitzacions (Socrata: contractes, menors, CPV, prorrogues; pscp: enriquiment) nomes es podien llançar per codi i l'historial (`sync_runs`, `sync_item_logs`, [04-model-de-dades.md](../docs/04-model-de-dades.md)) nomes es veia per BD. API + pantalla `/admin/sync` ([08-hub-integracions.md](../docs/08-hub-integracions.md) §3: «tota sincronitzacio deixa un run auditable»; regla UI-first).

## Comportament

### API (accions A2 ja existents: `sync:read` per consultar, `sync:execute` per llançar — admin i PM)

- `GET /sync-runs` — keyset per `id` desc (`page[size]` ≤ 100); filtres `filter[kind]`, `filter[status]`. Camps: kind, trigger, status, started/finished, comptadors (new/updated/unchanged/total_source), endpoint, `error_summary`.
- `GET /sync-runs/{id}/items` — detall per registre problematic del run (keyset per id desc, `page[size]` ≤ 200): file_code, outcome, message.
- `POST /sync-runs/actions/trigger` — cos `{kind, full?, limit?}` amb `kind ∈ {contracts, minor, cpv, extensions, enrichment}`:
  - mapa a jobs existents: `sync.contracts`, `sync.minor_contracts`, `sync.cpv`, `sync.extensions`, `enrich.batch` (enrichment: `full` → `force`, `limit` opcional).
  - `trigger` del run: `manual` per a usuaris, `api` per a claus de servei (mai ve del client).
  - dedup per tipus (`dedup_key = trigger:<job_type>`): un segon llançament amb un d'equivalent en cua/curs → 409.
  - resposta 202 amb `{job_id, job_type}` (el progres es consulta amb `GET /jobs/{id}`); auditoria `sync.trigger`.

### Pantalla /admin/sync (entrada de menu «Sincronitzacions», zona administracio, accio `sync:read`)

- Botons de llançament per tipus (enriquiment massiu amb confirmacio: pot trigar molt i pica un servei extern); el 409 de dedup es mostra com a avis, no com a error.
- Taula de runs amb badge d'estat, comptadors, durada i origen (manual/programat/api); `error_summary` desplegable; fila expandible que carrega els item logs del run.
- Refresc automatic (5 s) mentre hi ha algun run `running`.

## Canvis d'API

`GET /sync-runs`, `GET /sync-runs/{id}/items`, `POST /sync-runs/actions/trigger` (tag `sync`). Cap canvi de dades.

## Seguretat

- Llançar es `sync:execute` (tambe per a claus de servei amb aquest scope); el camp `trigger` es determina al servidor.
- Les crides externes van al job (cua), mai dins la request.

## Fora d'abast

- Programacio configurable per pantalla (els horaris viuen a `app/jobs/schedule.py`); cancel·lacio de runs (es fa via `POST /jobs/{id}/actions/cancel`).

## Criteris d'acceptacio

- [x] Llançament de cada tipus encua el job correcte amb dedup; segon llançament → 409.
- [x] Historial amb filtres i item logs; employee → 403.
- [x] Pantalla amb llançament, refresc i detalls.
- [x] Bateries verdes.
