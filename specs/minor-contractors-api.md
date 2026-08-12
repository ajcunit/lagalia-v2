# API de menors, adjudicataris i duplicats (Estat: implementada)

## Context i objectiu

Sisena PR de la Fase 1 ([05-api.md](../docs/05-api.md) §3): contractes menors amb abast departamental, rànquing unificat d'adjudicataris amb fitxa, i la cua de duplicats per NIF amb resolució. Completa la superfície de lectura/gestió del nucli; les accions i exports de contractes van a la PR següent.

## Comportament

Regles verificables:

- **Menors** (`minor_contracts:read` — admin/pm complet, dm/employee departamental; `minor_contracts:update` — admin/pm):
  - `GET /minor-contracts`: mateixa disciplina que contractes — **el predicat departamental s'aplica a llistat i detall** (M2M `minor_contract_departments`; els menors no tenen responsables); fora d'abast → `404`. Filtres: `q` (expedient/descripció/adjudicatari), `filter[fiscal_year]`, `filter[contract_type]`, `filter[department_id]`, `filter[unassigned]`, `filter[settled]` (amb/sense liquidació); ordre `award_date|award_amount|file_code` (±); keyset.
  - `GET /minor-contracts/{id}`: detall complet (adjudicació + liquidació + adjudicatari).
  - `PATCH /minor-contracts/{id}`: `internal_status` i `department_ids` (substitució del conjunt) — l'única edició de la matriu («Editar / assignar departaments»); auditat.
- **Adjudicataris** (acció `contracts:read`; **decisió v2 anotada**: el rànquing s'agrega sobre TOTES les dades — són dades de font pública — encara que l'usuari tingui abast departamental als expedients):
  - `GET /contractors`: rànquing unificat majors+menors per adjudicatari — comptadors i imports totals de cadascun i suma; `q` per nom (canònic o àlies) o NIF; ordre `total_amount|contracts_count|name` (±); keyset per (clau, id).
  - `GET /contractors/{id}`: fitxa (dades + KPIs) i **històric navegable**: contractes i menors (ids i resums, limitats i paginables via les APIs pròpies amb `filter[contractor_id]`).
- **Duplicats d'adjudicatari** (`duplicates:manage` — admin/pm):
  - `GET /contractors/duplicates?status=`: parells amb les dues fitxes incrustades per a la comparativa.
  - `POST /contractors/duplicates/{id}/actions/resolve` amb `action: merge_1|merge_2|reject`:
    - `merge_N`: guanya el contractor indicat; el perdedor transfereix contractes majors i menors, el seu nom esdevé `contractor_alias` del guanyador (les ingestes futures ja resolen soles), els seus àlies es reassignen, i **s'elimina** — *decisió v2 (matisa [04-model-de-dades.md](../docs/04-model-de-dades.md) §2)*: com que els parells tenen FK `CASCADE`, la fila del parell fusionat desapareix amb el perdedor; **la traça durable de la fusió és l'entrada d'auditoria** (`contractors.merge`, amb noms i ids) i l'àlies creat. Els altres parells pendents del perdedor es descarten (la detecció següent els regenera contra el guanyador si toca).
    - `reject`: el parell persisteix amb `status=rejected`, `resolved_by`/`resolved_at`, i no es regenera (la detecció fa `ON CONFLICT DO NOTHING` sobre el parell).
    - Tot auditat (`contractors.merge` / `contractors.duplicate_rejected`).

## Canvis d'API

`openapi.yaml`: tags `minor-contracts` i `contractors`, esquemes i camins nous. Client TS regenerat.

## Canvis de dades

Cap migració.

## Seguretat i permisos

- Tot per `Authorize(...)`; menors fora d'abast → `404`; denegacions auditades.
- La fusió és una acció destructiva reversible només per traçabilitat (auditoria + àlies); la UI hi posarà confirmació forta (10-ui §5).

## Fora d'abast

- Accions/exports/stats/facets de contractes i `bulk/assign-departments` (majors i menors): PR F1-7.
- Duplicats de **contractes** (detecció + cua): amb les alertes (PR F1-7), on viu la lògica de comparació.
- Vistes materialitzades del rànquing (04 §2): si el rendiment ho demana; ara agregats directes amb índexs.

## Criteris d'acceptació

- [x] IDOR de menors: employee d'un altre departament → `404` al detall; llistat filtrat; admin/pm complet.
- [x] PATCH de menors substitueix departaments i audita; employee → `403`.
- [x] Rànquing: adjudicatari amb 1 major (1000) + 2 menors (200+300) → `contracts_count=1`, `minor_count=2`, `total_amount=1500`; cerca per NIF i per àlies.
- [x] Fusió: contractes i menors reassignats, àlies creat, perdedor eliminat, parell fora de la cua i fusió auditada; segona detecció no reobre el parell rebutjat ni recrea el fusionat.
- [x] Bateries backend/frontend verdes; contracte validat; client TS regenerat.
