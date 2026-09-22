# BPM: seqüències de tasques per expedient (Estat: implementada)

## Context i objectiu

Petició d'usuari (2026-08-20): poder definir **seqüències de tasques** (processos) que s'engeguin soles quan un contracte és nou o quan la sincronització el porta a un estat concret, i que vagin **proposant la següent acció** al calendari de la persona, el departament o el rol que l'ha de fer, amb el ritme de dies indicat. Ha de ser un **mòdul activable** (specs/module-flags.md).

## Comportament

Donat un procés actiu amb passos definits,
Quan un contracte compleix el disparador (nou, o estat assolit),
Aleshores s'obre una instància del procés i es crea la tasca del primer pas; en completar-se cada tasca, la del pas següent apareix amb el desfasament de dies configurat, assignada segons el pas.

Regles verificables:

- **Procés** (`bpm_workflows`): nom, descripció, disparador (`contract_created` | `status_reached` | `manual`), `trigger_status` (text de l'estat de la font, només per a `status_reached`), actiu/inactiu. **Passos** (`bpm_steps`) ordenats: títol, descripció, tipus de tasca, `offset_days` (0–365), prioritat i **assignació** per `user` (usuari concret), `department` (la tasca queda al departament, visible per als seus membres) o `role` (s'assigna a tots els usuaris actius del rol).
- **Instància** (`bpm_instances`): una per contracte i procés (únic); estat `running|done|cancelled`, pas actual i tasca actual. Les tasques generades són tasques normals del mòdul de tasques (recordatoris, calendari, iCal i avisos ja existents s'hi apliquen sense fer res més).
- **Motor** (job `bpm.scan`, programat cada hora; també s'encua un escaneig en crear o arrencar manualment):
  - **Arrencada**: per a cada procés actiu, obre instàncies dels contractes que compleixen el disparador i no en tenen. Per no inundar amb l'històric: `contract_created` només per a contractes creats **després** del procés; `status_reached` només si el contracte s'ha actualitzat després de crear-se el procés. Límit de seguretat de 200 arrencades per procés i passada (es registra si es trunca).
  - **Avanç**: instància en marxa amb la tasca actual **completada** → crea la tasca del pas següent amb venciment = data de compleció + `offset_days` (mínim avui); si no hi ha més passos, la instància queda `done`. Tasca actual **cancel·lada o esborrada** → la instància queda `cancelled` (esborrar la tasca atura el procés, coherent amb les tasques periòdiques).
  - Amb el mòdul `bpm` desactivat, l'escaneig no fa res.
- **API** (prefix `/bpm`, tallat pel mòdul): CRUD de processos amb els passos (substitució sencera de la llista en editar), llistat d'instàncies (filtre per procés/contracte), `POST /bpm/workflows/{id}/actions/start` (arrencada manual sobre un contracte) i `POST /bpm/instances/{id}/actions/cancel`.
- Tota escriptura queda **auditada** (`bpm.workflow_*`, `bpm.instance_*`) i les tasques generades porten el rastre del procés al títol de l'historial habitual de tasques.

## Canvis d'API

`openapi.yaml`: tag `bpm` i rutes noves; esquemes `BpmWorkflow`, `BpmStep`, `BpmInstance`. Client TS regenerat.

## Canvis de dades

Migració `0036_bpm`: `bpm_workflows`, `bpm_steps` (únic `workflow_id+position`), `bpm_instances` (únic `workflow_id+contract_id`, FK `current_task_id → tasks SET NULL`). Cap canvi a `tasks`.

## Seguretat i permisos

- Accions noves a la matriu A2: **`bpm:read`** i **`bpm:manage`** — admin i responsable de contractació (qui orquestra la contractació). Cap check de rol als routers.
- Mòdul activable `bpm`: desactivat → 403 `module-disabled` a tot `/bpm/*` pel middleware existent; el job d'escaneig també s'atura.
- L'arrencada manual valida que el contracte existeix; les tasques generades respecten el modelatge de visibilitat existent del mòdul de tasques.

## UI

Entrada **«Processos»** al hub de configuració (acció `bpm:manage`, mòdul `bpm`): llista de processos a tot l'ample amb switch d'actiu, editor amb els passos (afegir/treure/ordenar per posició) i selector d'assignació (usuari/departament/rol), i vista d'instàncies amb estat i pas actual. Interruptor del mòdul a Configuració → Mòduls.

## Fora d'abast

- Branques condicionals, aprovacions o passos paral·lels (això seria un motor BPMN de veritat; aquí és una seqüència lineal).
- Disparadors per menors o per esdeveniments de webhook (extensió natural).
- Re-execució d'un procés sobre el mateix contracte sense cancel·lar la instància anterior.

## Criteris d'acceptació

- [x] Un procés amb disparador `contract_created` obre instància i primera tasca per a un contracte nou (i no per als anteriors al procés).
- [x] Completar la tasca d'un pas fa aparèixer la del següent amb el desfasament configurat; l'últim pas tanca la instància.
- [x] Assignació per usuari, departament i rol resolta correctament.
- [x] Esborrar o cancel·lar la tasca actual cancel·la la instància.
- [x] Amb el mòdul desactivat, `/bpm/*` respon 403 i l'escaneig no crea res.
- [x] Escriptures auditades; permisos per matriu (403 auditat per a rols sense concessió).
