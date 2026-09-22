# Visor de PDF intern (Estat: implementada)

## Context i objectiu

Petició d'usuari (2026-08-20): poder llegir els documents dels expedients **dins de l'aplicació**, sense haver-los de descarregar a la màquina local. Avui la pestanya de documents d'un contracte enllaça la font externa (PSCP) en una pestanya nova; la còpia local de MinIO només s'usava per al RAG i la revisió legal.

## Comportament

Donat un usuari amb accés a un contracte que té un document amb còpia local,
Quan clica «Visualitza» a la llista de documents,
Aleshores el PDF s'obre en un visor dins de l'aplicació (modal a pantalla gairebé completa), servit des de la còpia local, sense baixar cap fitxer al disc de l'usuari.

Regles verificables:

- **`GET /contracts/{id}/documents/{document_id}/content`** (autenticació estàndard per capçalera `Authorization` — cap token per query string): serveix el contingut de la còpia local.
  - Mateixa autorització que la resta de subrecursos del contracte: `contracts:read` + **abast departamental** via `get_scoped_contract` (la regla d'or de CLAUDE.md: l'abast s'aplica també als detalls i subrecursos).
  - Document d'un altre contracte o inexistent → 404; sense còpia local → 409 (`no-local-copy`).
  - El contingut **s'ensuma**: si comença per `%PDF-` es serveix `application/pdf` amb `Content-Disposition: inline`; qualsevol altra cosa, `application/octet-stream` amb `attachment` (mai s'executa res al navegador). Sempre `X-Content-Type-Options: nosniff` i `Cache-Control: no-store`.
  - Cada visualització queda **auditada** (`contracts.document_view`).
- **Frontend**: botó «Visualitza» (icona ull) només quan `has_copy`; baixa el contingut amb `fetch` autenticat, crea un object URL i el mostra en un `<iframe>` (visor natiu del navegador). Si el contingut no és PDF, s'ofereix com a descàrrega. L'object URL es revoca en tancar. Tancament amb Escape i botó.
- **CSP**: el visor usa `blob:` com a origen de l'iframe → el Caddyfile de producció afegeix `frame-src 'self' blob:`. `object-src` continua sent `none`.

## Canvis d'API

`openapi.yaml`: nou `GET /contracts/{id}/documents/{document_id}/content` (resposta binària). Client TS regenerat (el visor fa servir `fetch` directe per al blob, com l'export DOCX del generador).

## Canvis de dades

Cap. Es reutilitza `phase_documents.storage_key` (mai exposat: el que viatja és el contingut, no la clau).

## Seguretat i permisos

- Cap token per query string: l'iframe carrega un object URL creat al client a partir d'un `fetch` amb `Authorization` — el contingut no queda mai en cap URL compartible.
- Abast departamental aplicat al subrecurs; denegacions auditades pel motor central.
- El sniffing del tipus evita servir HTML/JS amb `inline` (XSS via document maliciós de la font): només els PDF s'obren al navegador.

## UI

Pestanya de documents de la fitxa del contracte: columna d'accions amb «Visualitza» (ull) quan hi ha còpia local; modal amb títol del document, botó de tancar i l'iframe a tota l'alçada disponible. L'enllaç extern a la font es manté com fins ara.

## Fora d'abast

- Documents de la fase d'execució i del generador documental (tenen els seus fluxos; extensió natural més endavant).
- Anotacions, cerca dins del PDF o miniatures (el visor natiu del navegador ja ofereix cerca i zoom).
- Visualització de formats no PDF (DOCX, etc.): es descarreguen com fins ara.

## Criteris d'acceptació

- [x] Un usuari amb accés veu el PDF al modal sense cap descàrrega al disc; per a un usuari d'un altre departament el contracte (i per tant el document) és un **404** — no se'n revela l'existència, mateix criteri que la resta de subrecursos.
- [x] Document sense còpia local → 409; document d'un altre contracte → 404.
- [x] Un fitxer que no és PDF mai se serveix `inline`.
- [x] Cada visualització deixa rastre a `audit_log`.
