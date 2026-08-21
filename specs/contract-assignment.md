# Assignació individual de departaments i responsables (Estat: implementada)

## Context i objectiu

Detectat en ús real (2026-08-20): des de l'edició d'un contracte no es podien assignar ni usuaris responsables ni departaments. Només existia l'assignació **massiva** de departaments des del llistat (specs/contract-actions.md), i la concessió `contracts:assign` de la matriu A2 («Assignar departaments / responsables») estava reservada sense cap endpoint que la fes servir. Els responsables, a més, no s'exposaven enlloc del detall.

## Comportament

Donat un admin o responsable de contractació,
Quan obre l'edició d'un contracte,
Aleshores hi veu la secció «Assignació» amb els departaments i els usuaris responsables, i pot canviar totes dues llistes; el canvi queda a l'historial del contracte i a l'auditoria.

Regles verificables:

- **`PUT /contracts/{id}/assignments`** (`contracts:assign`: admin i responsable de contractació, abast complet): cos `{department_ids, manager_ids}` (0–20 cadascun). **Substitueix les dues llistes senceres** — el cos és l'estat final, sense semàntica add/remove.
- Departament inexistent o usuari inexistent/inactiu → 422. Contracte inexistent → 404.
- Per cada llista que canvia de veritat: entrada d'**historial** (camp `departments` amb codis, camp `managers` amb noms, abans/després) i una entrada d'**auditoria** `contracts.assign` amb els camps canviats. Sense canvis reals, ni historial ni auditoria.
- El detall del contracte exposa **`managers`** (id i nom, res més); `department_ids` ja hi era.
- **`GET /users/options`** (`tasks:write`): usuaris actius amb **només id i nom** — els selectors d'assignació (responsables de contracte i assignats de tasques, specs/tasks-ui.md) necessiten anomenar usuaris sense obrir la gestió d'usuaris, que continua sent exclusiva d'admin (`users:read`). La porta és `tasks:write` perquè és el conjunt més ampli de rols que assigna (admin, RC, resp. de departament); els qui assignen contractes (admin, RC) també la tenen.

## Canvis d'API

`openapi.yaml`: nou `PUT /contracts/{id}/assignments`, nou `GET /users/options`, camp `managers` a `Contract`. Client TS regenerat.

## Canvis de dades

Cap migració: `contract_departments` i `contract_managers` existeixen des de la fase 1 (i l'abast departamental ja els fa servir per a la visibilitat).

## Seguretat i permisos

- `contracts:assign` (A2: admin ✔, responsable de contractació ✔) — fins ara reservada, ara usada. Cap check de rol al router.
- `GET /users/options` no filtra res per departament però només revela id i nom d'usuaris actius: el mínim per anomenar. Les dades completes d'usuari continuen darrere `users:read` (admin).
- En canviar els responsables canvia també **qui veu el contracte** (la visibilitat departamental inclou els responsables): és el comportament esperat i el motiu pel qual queda tot auditat.

## UI

Fitxa del contracte → «Edita»: secció **Assignació** (visible només amb `contracts:assign`) amb dues llistes de caselles — departaments i usuaris responsables — que es desen amb el mateix botó que la resta de l'edició. El resum de la fitxa mostra els departaments (amb nom) i els responsables assignats.

## Fora d'abast

- Assignació massiva de responsables des del llistat (la de departaments ja existeix; s'afegiria a specs/contract-actions.md si es demana).
- Notificar el responsable quan se l'assigna (candidat natural a webhook/recordatori; backlog si es vol).

## Criteris d'acceptació

- [x] Admin i responsable de contractació assignen departaments i responsables des de l'edició; el detall reflecteix el canvi a l'instant.
- [x] Historial i auditoria per cada llista canviada; res si no hi ha canvi real.
- [x] 422 per departament o usuari invàlid; 403 per a rols sense la concessió (auditat).
- [x] Un cop assignat, l'usuari responsable veu el contracte encara que no sigui del seu departament (visibilitat existent per responsables).
