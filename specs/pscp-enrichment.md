# Connector pscp i enriquiment (Estat: implementada)

## Context i objectiu

Setena PR de la Fase 1, primera meitat ([08-hub-integracions.md](../docs/08-hub-integracions.md) §2.2): el connector `pscp` (contractaciopublica.cat) que descarrega els JSON de fase de `phase_urls` i n'extreu els camps ampliats, criteris, mesa i documents — el que omple els buits de la fitxa. Com que l'esquema v1 no era als docs, **aquesta spec fixa l'estructura real verificada** (2026-08-12, expedient 2744/2026 de Cunit; fixtures a `tests/fixtures/pscp_*.json`).

## Esquema real verificat

- El JSON de fase té `publicacio` amb `dadesBasiquesPublicacio`, `dadesPublicacio`, `dadesPublicacioLot[]` i `dadesExpedient`; els textos són **multiidioma** (`{ca, es, en, oc}`) i els catàlegs `{id, ca, es…}`.
- **Licitació**: `dadesPublicacio.contracteHarmonitzat`, `preveuenProrroguesAlsPlecs`, `preveuenModificacionsAlsPlecs`, documents (`plecsDeClausulesAdministratives`, `documentsAprovacio`, `altresDocuments`, `memoriaJustificativaContracte`…); per lot: `criterisAdjudicacio`, `reservaSocial`, garanties, CPV.
- **Adjudicació**: per lot `importAdjudicacio`, `dataAdjudicacio`, `empresesAdjudicataries[]` (denominació, `identificador` NIF, tipus d'empresa), `peuDeRecurs`; `criterisAdjudicacio[]` amb `criteri` (catàleg), `ponderacio` i `desglossament[]`.
- **Documents**: llistes multiidioma d'objectes `{id, titol, hash, path, idioma, mida}`; descàrrega a `/portal-api/descarrega-document/{id}/{hash}` (el `path` és un testimoni xifrat intern del portal, **no** serveix per descarregar). `mida` és la mida en bytes.
- **Mesa**: absent als expedients petits; quan hi és, `dadesPublicacio.membresMesa[]` amb `{nom, cognoms, carrec}` — l'extracció és recursiva sota claus que contenen «mesa» (com feia la v1 — 02 §2.10). Criteris i mesa poden repetir-se entre fases: es dedupliquen per nom.

## Comportament

Regles verificables:

- **Emmagatzematge** (`core/storage.py`, resol B-003 per configuració): interfície única (`put/exists`) amb backend `filesystem` (`STORAGE_LOCAL_PATH`) o `s3` (MinIO/S3, `S3_*` de settings). Els documents es desen a `contracts/{id}/{fase}/{doc_id}-{nom-sanejat}` i la clau queda a `phase_documents.storage_key`.
- **Connector `pscp`** (hub, desactivat per defecte): client httpx amb **throttling respectuós configurable** (defecte 2 s/petició — el valor v1) i reintents; TLS verificat.
- **Extracció** (`integrations/pscp/extract.py`), amb multiidioma **ca→es→en**:
  - escalars promocionats: `is_harmonized`, `allows_extensions`, `allows_modifications`, `social_reserve`, `received_offers` (cerca recursiva de `nombreOfertes*`), i el conjunt complet d'escalars trobats dins `contracts.enrichment` (JSONB per fase);
  - `award_criteria` (delete+insert per contracte, idempotent) des de `criterisAdjudicacio`;
  - `committee_members` només sota claus que continguin «mesa» (mai `personesContacte` de l'òrgan);
  - `phase_documents` per (contracte, `source_doc_id`) amb títol, fase, `download_url` i mida; descàrrega a storage **opcional** (payload `download_documents`, defecte cert, amb límit de mida configurable).
- **Jobs**: `enrich.contract` (payload `contract_id`, `force`) i `enrich.batch` (`force` re-enriqueix; si no, només `enriched_at IS NULL` amb `phase_urls`); seqüencial amb el throttling del connector, progrés observable, `sync_run` kind `enrichment` amb comptadors, errors per expedient a `sync_item_logs`.
- El sync de contractes **no** encua enriquiment automàtic encara (arriba quan s'activi el connector en producció; anotat).

## Canvis d'API

Cap (l'exposició de criteris/mesa/documents a l'API i a la fitxa és la segona meitat de la F1-7).

## Canvis de dades

Cap migració (taules de la 0004).

## Seguretat i permisos

- URLs de descàrrega només del domini configurat del connector (anti-SSRF: es rebutja qualsevol document amb host diferent).
- Límit de mida per document; el contingut va a storage, mai a la BD.
- `enrichment` JSONB no conté dades personals més enllà de càrrecs públics de la font.

## Fora d'abast

- Exposició API/UI de criteris, mesa i documents (F1-7b).
- Indexació RAG (`rag.index_document`, Fase 3); `indexed_at` queda NULL.
- Encadenament automàtic post-sync i alertes (`alerts.recompute`).

## Criteris d'acceptació

- [x] Extracció sobre les fixtures reals: harmonitzat/pròrrogues/modificacions, adjudicatari amb NIF, documents amb id+títol+URL.
- [x] Multiidioma ca→es→en amb fallback.
- [x] enrich.contract idempotent (re-run sense force → skip; amb force → refresca) i documents a storage (backend filesystem als tests).
- [x] Anti-SSRF: document amb host estrany rebutjat.
- [x] Enriquiment real d'un contracte de Cunit verificat a BD.
- [x] Bateries verdes.
