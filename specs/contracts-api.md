# API de contractes — lectura i edició (Estat: implementada)

## Context i objectiu

Cinquena PR de la Fase 1: el nucli de l'API de contractes de [05-api.md](../docs/05-api.md) §3 amb l'**abast departamental aplicat també als detalls i subrecursos** — la correcció de l'IDOR, el defecte més greu de la v1 (A2 §4.1). Accions, exports, stats i assignació massiva arriben a la PR següent.

## Comportament

Donat un usuari autenticat,
Quan consulta o edita contractes,
Aleshores només veu i toca el que la matriu A2 i el seu abast li permeten, tant a llistats com a detalls, amb tota edició historiada.

Regles verificables:

- **Abast departamental** (A2 §3, un sol lloc: `contracts/repository.py`): amb accés `DEPT`, un contracte és visible si l'usuari **pertany a algun departament assignat** al contracte **o és a la llista de responsables**. Sense departaments ni responsabilitats → no veu res. El mateix predicat s'aplica a `GET /contracts`, `GET /contracts/{id}` i a tots els subrecursos (historial, pròrrogues, modificacions): **un detall fora d'abast és `404`** (no `403`: no es revela l'existència).
- **`GET /contracts`**: paginació keyset (`page[size]` 1–500), ordre `published_at|calculated_end_date|award_amount|file_code` (± prefix `-`), filtres de la Fase 1: `q` (cerca lliure per expedient/objecte/nom d'adjudicatari), `filter[department_id]` (∅ = «sense departament» amb `filter[unassigned]=true`), `filter[contract_type]`, `filter[status]`, `filter[internal_status]`, `filter[expiry_warning]`, `filter[possibly_finished]`, `filter[year]` (exercici de `published_at`), `filter[contractor_id]`. `?view=user|all` validat contra el rol (motor PR F0-4). La resta de filtres de 02 §2.4 i el `group_by=file` arriben amb la pantalla (anotat).
- **`GET /contracts/{id}`**: detall complet + **lots germans** (altres files del mateix `file_code`) + comptadors (pròrrogues, modificacions, historial).
- **Subrecursos**: `/history` (paginat simple, descendent), `/extensions`, `/modifications` — mateix abast que el detall.
- **`PATCH /contracts/{id}`** segons matriu:
  - `contracts:update` (admin/pm): `subject`, `contract_type`, `procedure`, `processing_type`, `internal_status`, `warning_months_override`;
  - només `contracts:update_warning` (dept_manager, dins d'abast): únicament `warning_months_override`; qualsevol altre camp → `403`;
  - cada camp canviat → entrada d'historial `manual` amb l'usuari; auditoria `contracts.update` amb noms de camps.
- **`POST /contracts`** (alta manual, `contracts:create`): camps bàsics + departaments; `source='local'`; historial no (neix); auditat.
- Contractes `source='external'` (importats pel SuperBuscador en el futur) **mai** apareixen als llistats operatius… *matís*: els sincronitzats també són `external`; el que exclou el llistat és `internal_status='rejected'`? — **Decisió v2**: el llistat mostra `source` extern i local; l'exclusió del 02 §2.11 es refereix als importats amb `origen='extern'` *del SuperBuscador*, que a la v2 es modelaran amb un flag propi quan arribi la feature (anotat aquí per no perdre-ho).

## Canvis d'API

`openapi.yaml`: tag `contracts`, esquemes `ContractSummary`, `Contract`, `ContractCreate`, `ContractUpdate`, `ContractHistoryEntry`, `ContractExtension`, `ContractModification` i els camins de lectura/edició. Client TS regenerat.

## Canvis de dades

Cap migració.

## Seguretat i permisos

- Tot per `Authorize(...)`; denegacions auditades; detalls fora d'abast → `404`.
- El `raw` i el `content_hash` no s'exposen mai per API (interns de sync).
- `q` va per paràmetres vinculats (ILIKE escapat), mai concatenació.

## Fora d'abast

- Accions (`finish`, `dismiss-expiry`, `enrich`, `open-in-gestiona`), `bulk/assign-departments`, exports, `stats`, `facets`, `group_by=file` (PR F1-6).
- Assignació de departaments/responsables per API (`contracts:assign`, PR F1-6).

## Criteris d'acceptació

- [x] IDOR: un `employee` d'un altre departament rep `404` al detall, a l'historial i a les pròrrogues d'un contracte que no és seu.
- [x] El mateix contracte és visible per: membre del departament assignat, responsable del contracte, admin.
- [x] Employee sense departaments → llistat buit (`total: 0`).
- [x] `dept_manager` pot canviar `warning_months_override` d'un contracte seu; si toca `subject` → `403`; fora d'abast → `404`.
- [x] PATCH d'admin genera historial `manual` per camp + auditoria.
- [x] Filtres i ordenació bàsics amb paginació keyset estable.
- [x] Contracte validat (Redocly) + client TS regenerat; bateries verdes.
