# Selector de vista i barra d'avisos (Estat: implementada)

## Context i objectiu

Petició de l'Esteve (2026-08-19): un usuari pot ser de diversos
departaments i ha de poder triar quina vista vol — un departament
concret, tots els seus, o tot l'ens (si el rol ho permet, cas admin). La
barra superior passa a ser l'indicador d'avisos i el lloc d'aquesta tria;
tancar sessió i mode fosc van a un desplegable a la targeta d'usuari.

## Comportament

### Vista (`?view=`)

- Gramàtica ampliada: `user` (els meus departaments, per defecte) ·
  `all` (tot l'ens) · **`dept:<id>`** (un departament concret).
- **Validació al servidor, mai confiança en el client**
  (`authz.resolve_view_scope`): `all` exigeix Vista Admin (com fins ara);
  `dept:<id>` exigeix ser membre del departament **o** Vista Admin —
  altrament 403 auditat.
- El frontend té un estat global de vista (`ViewProvider`), persistit per
  usuari a localStorage i **revalidat en carregar** (si la tria guardada
  ja no és vàlida per canvi de rol/departaments, cau al valor segur).
- Superfícies connectades: llistat i tauler de contractes, facetes,
  menors. La resta de llistats continuen amb l'abast per defecte (tots
  els departaments de l'usuari); s'hi aniran connectant (BACKLOG B-018).

### Barra superior

- **Selector de vista** (esquerra): «Tot l'ens» (si Vista Admin), «Els
  meus departaments» i una entrada per departament de l'usuari. Amagat
  quan no hi ha res a triar (un sol departament i sense Vista Admin).
- **Avisos** (dreta), de `GET /me/notices?view=` (refresc cada 60 s),
  cada un enllaça a la pantalla corresponent:
  - tasques pròpies obertes (i vençudes, en vermell, si n'hi ha);
  - contractes amb avís de venciment dins la vista;
  - contractes pendents de revisió dins la vista.
- Les tasques són **personals** (assignades a l'usuari), no canvien amb
  la vista; els comptadors de contractes sí.

### Menú d'usuari (sidebar)

La targeta d'usuari del peu del sidebar és un botó desplegable
(`role=menu`, tanca amb Escape i clic fora) amb **mode fosc/clar** i
**tancar sessió**; desapareixen de la barra superior.

## Canvis d'API

`GET /me/notices` (nou; tag `me`, sessió) i paràmetre `ViewScope` ampliat
amb `dept:<id>` (openapi + client TS regenerat).

## Seguretat

- La vista és una *petició* del client: el servidor la revalida sempre
  contra el rol i els departaments reals; denegacions auditades.
- Els comptadors d'avisos apliquen el mateix abast que les dades.

## Fora d'abast

- Estendre el selector a tasques, adjudicataris i alertes (B-018).
- Notificacions push/temps real (els avisos són sondeig de 60 s).

## Criteris d'acceptació

- [x] `dept:<id>` de membre → dades només d'aquell departament; de no
  membre sense Vista Admin → 403 auditat.
- [x] Selector persistent per usuari i revalidat; avisos per vista.
- [x] Desplegable d'usuari amb mode fosc i tancar sessió; barra neta.
- [x] Bateries verdes.
