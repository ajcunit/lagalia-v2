# Estadístiques i facets de contractes (Estat: implementada)

## Context i objectiu

Cinquena i última peça de la F1-7 ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.3, [05-api.md](../docs/05-api.md)): els KPIs del dashboard amb dades reals i els valors distincts per als filtres del llistat.

## Comportament

Regles verificables:

- **`GET /contracts/stats`** — permís `contracts:read`; abast com al llistat (`?view=user|all`, validat al servidor; ✔ᴰ només veu els seus números). Filtres: `filter[year]` (exercici de publicació), `filter[amount_min]`/`filter[amount_max]` (import d'adjudicació). Retorna:
  - `totals`: contractes visibles, `new_this_month` (publicats el mes en curs), `expiry_warning`, `possibly_finished`, `awarded_total` (∑ import adjudicació), `unique_contractors`;
  - `minors`: `count` i `amount` (mateix abast departamental via `minor_contract_departments`; el filtre d'any hi aplica per `fiscal_year`);
  - `by_status`: recompte per estat (descendent);
  - `by_department`: recompte per departament (descendent, només departaments amb contractes visibles);
  - `top_contractors`: 10 adjudicataris per volum adjudicat (id, nom, import, recompte).
- **`GET /contracts/facets`** — permís `contracts:read`, mateix abast. Valors distincts no nuls i ordenats de: `statuses`, `contract_types`, `procedures`, `years` (exercicis de publicació, descendent). Per omplir els selectors del llistat; sense recomptes (no filtren res, són opcions).
- Les agregacions són **set-based** (una consulta per bloc); mai s'itera per files a Python.

## Canvis d'API

`openapi.yaml`: `GET /contracts/stats` (esquema `ContractStats`) i `GET /contracts/facets` (esquema `ContractFacets`). Client TS regenerat.

## Canvis de dades

Cap.

## Seguretat i permisos

- El predicat de visibilitat del repositori s'aplica a **totes** les agregacions (contractes, menors, departaments, adjudicataris): els números d'un `employee` no revelen mai res de fora del seu abast.
- `?view=all` sense dret → 403 auditat (mateix mecanisme del llistat).

## UI

- **Dashboard**: targetes KPI (total, nous del mes, fi propera, possiblement finalitzats, volum adjudicat, menors, licitadors únics) — cada targeta **enllaça al llistat filtrat**; resum per estat clicable; top 10 adjudicataris i contractes per departament com a barres horitzontals (sense llibreria de gràfics, accessibles com a llistes); filtre d'exercici.
- **Llistat**: els selectors d'estat i tipus s'omplen amb els facets (abans no existien opcions).

## Fora d'abast

- Gràfic semicircular i tooltips per expedient (quan hi hagi llibreria de gràfics, si cal).
- KPIs nous de la v2 (renovacions crítiques, temps mitjà de tramitació…) — arriben amb les tasques/validacions.
- Stats de menors més enllà del bloc `minors`.

## Criteris d'acceptació

- [x] KPIs correctes i per abast (admin ho veu tot; employee només el seu departament).
- [x] Filtre d'exercici aplicat a majors (publicació) i menors (fiscal_year).
- [x] Facets distincts, ordenats i per abast.
- [x] Dashboard amb targetes enllaçades i llistat amb selectors plens.
- [x] Bateries verdes; client TS regenerat.
