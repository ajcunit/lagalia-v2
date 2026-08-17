# SuperBuscador: registre public de tot Catalunya (Estat: implementada)

## Context i objectiu

Funcio estrella de la v1 (02 §2.10): cercar al dataset obert de contractacio de TOTA Catalunya (sense filtre d'organisme propi), explorar la fitxa externa amb les seves fases i descarregar-ne documents. Ruta `/search` (zona Intel·ligencia, accio `tools:use`).

## Comportament

### API (accio `tools:use`; tag `public-registry`; 05 §referencia-i-cerca)

- `GET /public-registry/search` — proxy Socrata **parametritzat** (mai SoQL cru; tot passa pel query builder):
  - `q` (cerca de text completa `$q`), `filter[organisme]` (conte, case-insensitive, sobre `nom_organ`), `filter[amount_min]`/`filter[amount_max]` (sobre `pressupost_licitacio_amb`), `filter[from]`/`filter[to]` (sobre `data_publicacio_anunci`), `filter[contract_type]` (igualtat), `filter[phase]` (igualtat sobre `fase_publicacio`; ampliacio 2026-08-17).
  - Paginacio per pagina (`page`, `page_size` ≤ 50; `$limit`/`$offset`; `meta.has_more` demanant-ne un de mes — el dataset no dona total barat).
  - Ordre fix: `data_publicacio_anunci` desc.
  - Resposta en targetes: file_code, lot, subject, organisme, departament, tipus, procediment, estat, data de publicacio, pressupost (amb IVA), import d'adjudicacio, adjudicatari, `phase_urls` i `links`.
- `GET /public-registry/contracts/{file_code}` — totes les files (lots/fases) del codi al dataset, mapades senceres; 404 si no existeix.
- `GET /public-registry/phase?url=` — proxy **validat** del JSON de fase: la URL ha de ser del domini del connector pscp (anti-SSRF, `_check_host`); retorna `{documents, committee, criteria}` extrets amb els extractors existents de l'enriquiment. Autenticat per sessio (cap token per query string).

> ⚠️ DESVIACIÓ CONTROLADA de «cap crida externa dins d'una request»: 05 §API defineix
> explicitament aquests endpoints com a proxy interactiu de nomes lectura. Mitigacions:
> timeout curt (15 s), throttle del connector, cap escriptura, errors com a Problem 502
> sense eco de la peticio.

### Pantalla /search

- Barra de cerca gran + filtres (organisme, tipus de contracte i fase com a desplegables amb els valors reals del dataset, rang d'imports, rang de dates) i boto «Neteja els filtres (N)» per descartar criteris d'un cop. **Estat a la URL** (querystring): una cerca es pot enllaçar/compartir i el navegador recorda enrere/endavant.
- Resultats en **targetes**: objecte, organisme, expedient+lot, badges de tipus/estat, data, imports i adjudicatari. Paginacio Anterior/Seguent.
- **Fitxa externa** (nomes lectura; redisseny 2026-08-17): pagina propia
  `/search/detail?code=<expedient>` en clicar el titol d'una targeta, amb
  **pestanyes** (Resum · Documents · Lots i fases): capçalera (xip
  d'expedient, titol, organisme, badge d'estat, boto «Desa» i enllaç al
  portal); Resum = **cronograma del proces** (anunci previ → publicacio →
  licitacio → adjudicacio → formalitzacio → fi, amb estats fet/proper/
  pendent), targeta de **CPVs amb descripcions resoltes del cataleg
  sincronitzat** (GET /cpv per prefix de codi), targeta «Informacio rellevant»
  (objecte, informacio general, dates, imports, adjudicatari), **criteris
  d'adjudicacio amb barres de ponderacio** (del JSON de la fase de licitacio)
  i targeta de l'**organ de contractacio**; Documents = **carpetes per fase**
  (lucide Folder/FolderOpen, carrega en obrir, icona pel tipus de fitxer
  segons extensio, «＋ projecte» per document); Lots = taula per fila
  lot/fase. Components compartits amb la fitxa municipal
  (`components/contractSheet.tsx`: Timeline, CriteriaBars, CpvChips,
  InfoPair, SheetTabs; `components/FileTypeIcon.tsx`). Iconografia lucide
  homogenia (sense emojis).
- `GET /public-registry/contracts/{file_code}` usa el convertidor `:path`
  perque els codis d'expedient porten barres (p. ex. `6477/2026`).
- Buits i errors amb missatges clars; imports formatats; WCAG (focus, aria, taules amb capçaleres).

## Canvis d'API

`GET /public-registry/search`, `GET /public-registry/contracts/{file_code}`, `GET /public-registry/phase` (tag `public-registry`). Cap canvi de dades.

## Seguretat

- Tot filtre passa pel query builder SoQL (validacio de camps, literals escapats, numerics/dates tipats). El paràmetre `q` viatja com a `$q` (parametre HTTP, mai concatenat a `$where`).
- El proxy de fase nomes accepta URLs del host del connector pscp (whitelist per hostname).
- Sense escriptures; res del cos/peticio als errors.

## Fora d'abast (seguent PR)

- ~~**Favorits** (02 §2.11)~~ → implementat, vegeu specs/favorites.md (snapshot JSONB, mai a `contracts`).
- ~~Enviar documents al generador~~ → implementat, vegeu specs/docgen-external-refs.md («＋ projecte» a l'explorador de fases, amb creacio de projecte al vol).

## Criteris d'acceptacio

- [x] Cerca amb filtres combinats contra el dataset real; paginacio.
- [x] Fitxa externa amb fases, documents descarregables i mesa.
- [x] URL de fase fora del domini pscp → 422; sense permis → 403.
- [x] Estat de cerca a la URL; bateries verdes.
