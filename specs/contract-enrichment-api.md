# Exposició de l'enriquiment a l'API i a la fitxa (Estat: implementada)

## Context i objectiu

Segona meitat de la F1-7 ([specs/pscp-enrichment.md](pscp-enrichment.md) la va deixar fora d'abast): els criteris d'adjudicació, la mesa de contractació i els documents de fase que l'enriquiment desa a la BD han de ser visibles a l'API i a la fitxa del contracte — són els buits de la fitxa detectats amb dades reals.

## Comportament

Regles verificables:

- **Tres subrecursos nous de només lectura**, amb el mateix patró d'abast que pròrrogues/modificacions (`contracts:read`, la visibilitat departamental s'aplica al subrecurs i fora d'abast → 404, mai 403):
  - `GET /contracts/{id}/criteria` → criteris ordenats per `position`, amb `name`, `weight` i `breakdown` (JSON original de la font).
  - `GET /contracts/{id}/committee` → membres de la mesa (`first_name`, `last_name`, `role`).
  - `GET /contracts/{id}/documents` → documents de fase ordenats per fase i id, amb `phase`, `title`, `doc_type`, `size`, `download_url` (URL pública del portal) i `has_copy` (hi ha còpia a l'emmagatzematge local).
- `storage_key` **no s'exposa mai** (detall d'infraestructura); la descàrrega de la còpia local arribarà amb els tokens efímers de descàrrega (06 §…, mateixa peça que els exports).
- **Fitxa (UI)**: tres seccions noves — «Criteris d'adjudicació» (taula posició/criteri/ponderació), «Mesa de contractació» (llista amb càrrec) i «Documents» (agrupats per fase, amb mida formatada i enllaç al portal en pestanya nova). Les seccions només es mostren si tenen dades; si el contracte no està enriquit es manté l'avís existent d'enriquiment pendent.

## Canvis d'API

`openapi.yaml`: esquemes `AwardCriterion`, `CommitteeMember` i `PhaseDocument`; rutes `GET /contracts/{id}/criteria`, `/committee` i `/documents`. Client TS regenerat.

## Canvis de dades

Cap (taules de la 0004, poblades per l'enriquiment).

## Seguretat i permisos

- `contracts:read` + abast departamental efectiu també als tres subrecursos (anti-IDOR: 404 fora d'abast).
- `breakdown` és JSON de la font pública; no conté secrets ni dades personals més enllà de càrrecs públics.

## Fora d'abast

- Descàrrega de la còpia local dels documents (token efímer d'un sol ús; amb els exports de la F1-7c).
- Accions de contracte (enriquir des de la UI, finalitzar…) i indexació RAG.

## Criteris d'acceptació

- [x] Els tres subrecursos retornen les dades de l'enriquiment ordenades i sense `storage_key`.
- [x] Fora d'abast departamental → 404 als tres subrecursos.
- [x] Fitxa amb criteris, mesa i documents visibles per a un contracte enriquit; seccions absents si no hi ha dades.
- [x] Client TS regenerat; bateries verdes.
