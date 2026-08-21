# Sincronització nocturna programada (Estat: implementada)

## Context i objectiu

docs/08 §3 prescriu `sync.contracts` amb «cron configurable (hora, dies,
TZ) + manual» i les extensions encadenades després. Fins ara totes les
sincronitzacions de dades es llançaven només a mà des de la pantalla.

## Comportament

### Job `sync.nightly` (orquestrador)

Executa la cadena completa **en ordre i en sèrie** (l'ordre importa: les
extensions i l'execució referencien contractes acabats de sincronitzar):

1. `sync.contracts` (majors)
2. `sync.extensions` (RPC: pròrrogues, modificacions, liquidacions)
3. `sync.minor_contracts` (menors)
4. `sync.execution` (dataset d'execució + enriquiment de detall)

- Reutilitza els handlers registrats (mateix codi que el llançament
  manual: `sync_runs`, dedup i auditoria per pas inclosos).
- Un pas que falla **no atura la cadena**: es registra i es continua; el
  job acaba `failed` si algun pas ha fallat (amb el resum de tots) i
  `succeeded` si tots han anat bé. Sense reintents propis
  (`max_attempts=1`): la nit següent ja tornarà, i el re-encuament manual
  sempre hi és.
- Progrés observable: percentatge i missatge per pas.

### Programació configurable (settings coneguts)

- `sync.nightly_enabled` — `true`/`false` (per defecte `true`).
- `sync.nightly_time` — hora local `HH:MM` (per defecte `02:30`),
  sempre en **Europe/Madrid**.
- `sync.nightly_days` — llista JSON de dies ISO (1=dilluns … 7=diumenge;
  per defecte tots).

El scheduler (procés `app.jobs.scheduler`, advisory lock) llegeix la
configuració de la BD a cada tick i encua `sync.nightly` **un cop al
dia** quan l'hora local passa de l'hora configurada en un dia actiu
(clau Redis `sched:sync.nightly:<data>` + dedup de cua): canviar l'hora
no requereix reiniciar res.

### Pantalla (UI-first)

Targeta «Programació nocturna» a Sincronitzacions: commutador, hora,
dies de la setmana i última execució de la cadena; escriu els settings
via l'API existent (`config:write`). El llançament manual per tipus no
canvia.

## Canvis d'API

Cap endpoint nou: settings coneguts via `GET/PUT /settings` existents.
`sync.nightly` apareix a `GET /jobs` i a la safata com qualsevol job.

## Fora d'abast

- Cadències separades per tipus (una sola cadena nocturna cobreix la
  prescripció actual; si mai cal, s'afegiran settings per tipus).

> Actualització 2026-08-21: `alerts.recompute` ja **és l'últim pas de la
> cadena nocturna** (i va programat diàriament com a xarxa de seguretat) —
> vegeu specs/contract-actions.md. Era aquí a fora d'abast i ningú el va
> encuar mai: a producció els venciments no s'omplien.
- `sync.cpv` (manual/trimestral segons docs/08): queda manual.

## Criteris d'acceptació

- [x] Cadena nocturna en ordre, tolerant a fallades per pas, observable.
- [x] Hora/dies configurables des de la pantalla, efectius sense reinici.
- [x] Un sol dispar per dia encara que el scheduler faci molts ticks.
- [x] Bateries verdes.
