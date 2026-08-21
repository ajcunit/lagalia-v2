# Pantalles de tasques (Estat: implementada)

## Context i objectiu

UI del mòdul de tasques ([tasks-core.md](tasks-core.md); [02](../docs/02-especificacio-funcional.md) §2.19 «Vistes»). Només frontend sobre l'API existent.

## Comportament

- **/tasks** (entrada nova «Tasques» a operacions, amb `tasks:read`): dues vistes commutables:
  - **Llista** («Les meves tasques»): ordenada per venciment, filtre d'estat (pendents per defecte), badge de vençudes (data passada), accions ràpides *Comença* / *Completa* / *Cancel·la* segons estat; enllaç al contracte o menor associat.
  - **Calendari mensual**: graella dl–dg, navegació mes anterior/següent, tasques com a xips al seu dia (color per prioritat), clic → expedient associat. Accessible: taula amb capçaleres de dia.
- **Suggeriments** (a dalt de /tasks, només si `tasks:write`): les propostes de les alertes amb el botó **Planifica** — crea la tasca amb tipus, títol i venciment prefixats (venciment = data final del contracte).
- **Fitxa de contracte**: secció «Tasques» amb les obertes (acció ràpida de completar, **esborrar** amb confirmació per a qui té `tasks:write`) i **alta ràpida** amb títol, tipus, venciment, prioritat, **assignats** i **periodicitat** (petició d'usuari 2026-08-20: tasques de supervisió periòdiques per expedient):
  - Periodicitats: puntual, setmanal, mensual, trimestral, semestral, anual — etiquetes amables que mapen a RRULE (`FREQ=MONTHLY;INTERVAL=3`, etc.); el motor de recurrència ja existia a [tasks-core.md](tasks-core.md): **en completar** una tasca periòdica es genera la següent ocurrència amb els mateixos assignats i recordatoris. Mentre una ocurrència no es completa, no se'n generen de noves (la pendent és l'avís, i els recordatoris insisteixen); esborrar la tasca atura la sèrie.
  - Les tasques periòdiques es distingeixen amb un badge de la seva periodicitat.
  - El selector d'assignats es nodreix de `GET /users/options` (porta `tasks:write`, només id i nom — vegeu [contract-assignment.md](contract-assignment.md)); resol la decisió pendent que hi havia anotada sobre rols sense `users:read`.
- **Dashboard**: widget «Properes tasques» (5 més pròximes, obertes) amb enllaç a /tasks.
- **Suggeriments col·lapsats**: es mostren els 5 més urgents amb «Mostra'ls tots»; només a la vista llista (el calendari queda net).
- **Feed iCal** (`GET /me/tasks.ics?key=…`): subscripció des d'Outlook amb **clau opaca revocable** per usuari (`POST /me/ical-key` genera o regenera — regenerar revoca l'anterior; `DELETE` la revoca). El feed conté les tasques obertes de l'usuari (assignades o creades per ell). Mai el JWT per query string. Botó «Subscripció iCal» a /tasks que copia l'enllaç.
  - **Nota de desplegament**: l'Outlook web (i el «nou Outlook») baixen el feed des del núvol de Microsoft — cal que l'app sigui accessible per HTTPS des d'Internet (staging/producció); amb localhost només funcionen els clients d'escriptori (Outlook clàssic, Thunderbird). El reverse proxy ha de servir `/api/v1/me/tasks.ics` sense exigir sessió (la clau revocable és l'autorització).

## Fora d'abast

- Vista setmanal del calendari.
- Generació de la següent ocurrència per rellotge encara que l'anterior no s'hagi completat (el model actual és deliberat: la tasca pendent és l'avís; si es volgués acumulació per temps, entrada de backlog).

## Criteris d'acceptació

- [x] Llista amb accions ràpides i estats; calendari mensual navegable.
- [x] Suggeriment → Planifica → tasca creada i fora de la llista de suggeriments.
- [x] Alta ràpida des de la fitxa; secció només visible amb permís de lectura.
- [x] Widget al dashboard.
- [x] tsc/eslint/vitest verds.
