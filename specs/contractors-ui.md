# Pantalles d'adjudicataris (Estat: implementada)

## Context i objectiu

Rànquing, fitxa i revisió de duplicats d'adjudicataris ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.6) sobre l'API existent ([minor-contractors-api.md](minor-contractors-api.md)). Només frontend.

## Comportament

- **/contractors** (amb `contracts:read`, entrada nova a la navegació): rànquing unificat (majors + menors) amb cerca per nom/àlies/NIF i ordenació per volum total, nombre de contractes o nom; columnes: nom, NIF, contractes (majors i menors) i imports. Paginació per cursor.
- **/contractors/{id}** (redisseny 2026-08-18, per pestanyes): **Resum** (volum de contractació i contractes vinculats — la vista segueix `can_switch_view`: admin/gestor global, la resta el seu abast, esmena 2026-08-17), **Contacte** (dades d'empresa: NIF, nacionalitat, tipus, telèfon, correu; àlies coneguts) i **Anàlisi de mercat**.
- **Anàlisi de mercat** (petició de l'Esteve, 2026-08-18): amb quines administracions treballa l'adjudicatari a TOT Catalunya. `GET /public-registry/contractor-analysis?tax_id=` (tools:use, mateixa desviació controlada de proxy interactiu que el SuperBuscador) executa 4 consultes agregades via query builder (ampliat amb `select_aggregate`/`select_count_distinct`/`group_by`, funcions en whitelist i camps validats): totals (expedients totes les fases, administracions distintes, període d'activitat), imports (suma/mitjana sobre files de Formalització), rànquing d'organismes (top 20 per import) i desglossament per tipus. KPIs + taules a la pestanya; **res no s'escriu a les taules municipals** (només lectura en directe, nota visible).
- **Pestanya «Adjudicatari» a la fitxa del contracte**: dades completes de l'empresa (contacte, volum, nom a la font) amb enllaç a la fitxa completa.
- **Xifres coherents a l'anàlisi** (esmena 2026-08-18): el rànquing per organisme i el desglossament per tipus mostren SEMPRE els expedients publicats (totes les fases) i, a banda, els formalitzats amb els imports — així els KPI quadren amb les taules (abans el KPI comptava totes les fases i la taula només Formalització). KPI nou «Expedients formalitzats».
- **Desplegable per organisme**: cada fila del rànquing s'expandeix i llista els expedients de l'adjudicatari amb aquella administració (filtre nou `filter[contractor_nif]` al cercador públic, NIF exacte via query builder), enllaçats a la fitxa externa del SuperBuscador (`/search/detail`).
- **Contacte des del portal** (2026-08-18): els JSON de fase i d'execució porten `empresaContractista` (telèfon, correu, tipus d'empresa); l'enriquiment i el sync d'execucions omplen aquests camps al registre de contractistes NOMÉS quan són buits (mai trepitgen dades existents).
- **/contractors/duplicates** (amb `duplicates:manage` — admin i resp. contractació; entrada a la zona d'administració): parells pendents amb els dos candidats costat a costat (nom, NIF, volum), accions **Fusiona a l'1 / Fusiona al 2 / Rebutja** amb confirmació i notes opcionals; pestanya per veure els resolts. 409 (ja resolt) visible.
- > ⚠️ La revisió **agrupada per NIF** (B-011) queda pendent del backend; mentrestant la pantalla treballa amb parells i mostra l'avís del volum pendent.

## Canvis d'API

`GET /public-registry/contractor-analysis?tax_id=` (2026-08-18; openapi.yaml +
client TS regenerat). El query builder SoQL guanya agregacions validades.

## Criteris d'acceptació

- [x] Rànquing cercable i ordenable; fitxa amb àlies i enllaços.
- [x] Resolució de duplicats amb confirmació; errors visibles; llista de resolts.
- [x] Entrades de navegació noves amb els permisos correctes.
- [x] tsc/eslint/vitest verds.
