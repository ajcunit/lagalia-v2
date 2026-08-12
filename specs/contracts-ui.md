# Pantalles de contractes — llistat i fitxa (Estat: implementada)

## Context i objectiu

Primera pantalla operativa de la Fase 1 al frontend ([10-ui.md](../docs/10-ui.md), [02](../docs/02-especificacio-funcional.md) §2.4): el llistat de contractes amb filtres server-side i la fitxa amb seccions, sobre l'API de la PR F1-5/6.

## Comportament

Regles verificables:

- **L'estat viu a la URL** (10-ui §1.2): cerca, filtres, ordre, vista i cursor com a query params — Enrere, enllaços compartits i marcadors reprodueixen la vista exacta. La cerca lliure va amb debounce.
- **Taula server-side única**: ordenació clicant capçaleres (columnes numèriques amb `tabular-nums`), paginació per cursor (Següent/Anterior amb pila de cursors), `meta.total` real.
- **Filtres de la fase**: cerca lliure, departament (desplegable de `/departments`), exercici, tipus, estat intern, alerta de venciment, possiblement finalitzats, sense departament; chips d'actius amb «netejar-ho tot».
- **Vista Admin/Usuari**: toggle només si `can_switch_view` (de `/me/permissions`), sense recàrrega — canvia el param `view`.
- **Fitxa** (`/contracts/:id`): seccions d'objecte i gestió, adjudicatari (enllaç a fitxa futura), imports (formats `ca-ES` centralitzats: `formatCurrency`/`formatDate`/`formatDuration`, 10-ui §2), dates i durada, classificació, **lots germans** navegables, **pròrrogues**, **modificacions** i **historial** (primera pàgina); enllaços externs de `links` amb `rel="noopener"`; breadcrumb.
- **Estats**: càrrega (esquelet), buit dissenyat (amb causa: sense resultats vs sense permisos de res), error amb `Problem` + trace_id; 404 de fora d'abast → pàgina no trobada.
- **Permisos**: la pantalla no dedueix res del rol; la sidebar ja filtra per `contracts:read`. L'edició (PATCH) arriba amb la pantalla d'edició (posterior).
- **A11y**: taula amb `scope`, capçaleres d'ordenació com a botons amb `aria-sort`, filtres amb labels, axe verd a les dues pantalles.

## Canvis d'API

Cap (consumeix el contracte existent via client generat).

## Fora d'abast

- Edició inline, accions (finalitzar, descartar alerta), exports i selecció múltiple (amb la PR d'accions F1-7).
- `group_by=file` (deduplicació per expedient) — quan l'API l'ofereixi.
- Pantalles de menors i adjudicataris (PR següent, reutilitzant DataTable).

## Criteris d'acceptació

- [x] El llistat mostra dades reals paginades; filtres i ordre modifiquen la URL i la recàrrega reprodueix la vista.
- [x] La fitxa mostra seccions, lots germans, pròrrogues i historial reals.
- [x] Formats `ca-ES` amb tests (1234567.5 → «1.234.567,50 €»).
- [x] axe verd; bateria frontend verda; captura real amb dades de Cunit.
