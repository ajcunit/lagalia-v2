# Pantalles de tasques (Estat: implementada)

## Context i objectiu

UI del mòdul de tasques ([tasks-core.md](tasks-core.md); [02](../docs/02-especificacio-funcional.md) §2.19 «Vistes»). Només frontend sobre l'API existent.

## Comportament

- **/tasks** (entrada nova «Tasques» a operacions, amb `tasks:read`): dues vistes commutables:
  - **Llista** («Les meves tasques»): ordenada per venciment, filtre d'estat (pendents per defecte), badge de vençudes (data passada), accions ràpides *Comença* / *Completa* / *Cancel·la* segons estat; enllaç al contracte o menor associat.
  - **Calendari mensual**: graella dl–dg, navegació mes anterior/següent, tasques com a xips al seu dia (color per prioritat), clic → expedient associat. Accessible: taula amb capçaleres de dia.
- **Suggeriments** (a dalt de /tasks, només si `tasks:write`): les propostes de les alertes amb el botó **Planifica** — crea la tasca amb tipus, títol i venciment prefixats (venciment = data final del contracte).
- **Fitxa de contracte**: secció «Tasques» amb les obertes (acció ràpida de completar) i **alta ràpida** (títol, tipus, venciment, prioritat; assignats seleccionables només si el rol té `users:read` — limitació anotada: cal decidir si el llistat d'usuaris del departament s'obre a `departments:read`).
- **Dashboard**: widget «Properes tasques» (5 més pròximes, obertes) amb enllaç a /tasks.
- **Suggeriments col·lapsats**: es mostren els 5 més urgents amb «Mostra'ls tots»; només a la vista llista (el calendari queda net).
- **Feed iCal** (`GET /me/tasks.ics?key=…`): subscripció des d'Outlook amb **clau opaca revocable** per usuari (`POST /me/ical-key` genera o regenera — regenerar revoca l'anterior; `DELETE` la revoca). El feed conté les tasques obertes de l'usuari (assignades o creades per ell). Mai el JWT per query string. Botó «Subscripció iCal» a /tasks que copia l'enllaç.

## Fora d'abast

- Selector d'assignats per a responsables sense `users:read` (anotat com a decisió pendent).
- Vista setmanal del calendari.

## Criteris d'acceptació

- [x] Llista amb accions ràpides i estats; calendari mensual navegable.
- [x] Suggeriment → Planifica → tasca creada i fora de la llista de suggeriments.
- [x] Alta ràpida des de la fitxa; secció només visible amb permís de lectura.
- [x] Widget al dashboard.
- [x] tsc/eslint/vitest verds.
