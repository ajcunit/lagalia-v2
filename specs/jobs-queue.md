# Cua de treballs (Estat: implementada)

## Context i objectiu

Novena PR ([00-primers-passos.md](../docs/00-primers-passos.md) §4): la infraestructura de jobs que és prerequisit de la Fase 1 — tota crida a serveis externs va a la cua, mai dins d'una request ([03-arquitectura.md](../docs/03-arquitectura.md) §2.4). Inclou worker (arq), scheduler de procés únic amb advisory locks, `GET /jobs/{id}`, cancel·lació i SSE de progrés amb token efímer d'un sol ús.

## Comportament

Donat un job encuat per un servei de l'aplicació,
Quan el worker l'executa,
Aleshores el seu estat i progrés són consultables per `GET /jobs/{id}`, en temps real per SSE, i tota transició queda al registre durador (`jobs`).

Regles verificables:

- **Cua**: Redis + **arq**. L'id del job d'arq és el mateix UUID de la fila `jobs` (traçabilitat 1:1). `dedup_key` amb índex únic parcial (`status IN (queued, running)`) impedeix dues execucions concurrents del mateix treball (p. ex. una sola sync alhora).
- **Runner**: embolcalla tot handler registrat — marca `running`/`started_at`, exposa `set_progress(pct, message)` (escriu a la fila i publica a Redis pub/sub `job:{id}:events`), desa `result` i `success`, o `error` (mai el payload sencer) i `failed`; publica sempre l'esdeveniment terminal.
- **Scheduler**: procés únic efectiu encara que se n'aixequin rèpliques — `pg_try_advisory_lock` de sessió; qui no té el lock espera en standby. Les definicions periòdiques viuen a `app/jobs/schedule.py` (Fase 0: només `system.heartbeat`, que prova la maquinària de punta a punta).
- **`GET /jobs/{id}`** (autenticat): visible per al **creador** del job; per a la resta cal la concessió `sync:read` de la matriu A2 (admin/procurement_manager). Cap check de rol al router: propietat al servei + motor d'autorització.
- **`POST /jobs/{id}/actions/cancel`**: mateixa regla d'accés però amb `sync:execute` per a no-creadors; només jobs `queued`/`running` → `202` amb el job; estats terminals → `409`.
- **`POST /auth/ephemeral`** (contracte existent): emet un token opac d'un sol ús (60 s, Redis `SETEX`) lligat a `{usuari, purpose, resource}`. Per a `purpose=job_events` exigeix accés de lectura al job. Auditat (`auth.ephemeral`).
- **SSE `GET /jobs/{id}/events?token=`**: el token efímer es consumeix amb `GETDEL` (el segon ús falla amb `401`); mai s'accepta un JWT per query string. Emet l'estat actual en connectar, retransmet el pub/sub, envia heartbeats (`: ping`) i tanca en estat terminal. `Cache-Control: no-store`.
- **Contracte**: aquesta PR amplia `openapi.yaml` amb el tag `jobs`, l'esquema `Job` i els tres camins; el client TS es regenera.

## Canvis d'API

`openapi.yaml`: nous `GET /jobs/{id}`, `GET /jobs/{id}/events`, `POST /jobs/{id}/actions/cancel` i esquema `Job` (segons [05-api.md](../docs/05-api.md) §3). `POST /auth/ephemeral` passa de contracte a implementat.

## Canvis de dades

Migració `0003_jobs`: taula `jobs` segons [04-model-de-dades.md](../docs/04-model-de-dades.md) §4 — `id UUID`, `type`, `payload JSONB`, `status` enum (`queued|running|success|failed|cancelled`), `progress`, `progress_message`, `result JSONB`, `error`, `dedup_key` (únic parcial), `attempts`, `created_by FK SET NULL`, timestamps. `job_events` (opcional al model) es descarta de moment: el detall viu al pub/sub i als logs estructurats.

## Seguretat i permisos

- El progrés per SSE no exposa mai el `payload` del job (pot contenir referències internes); només estat, percentatge, missatge i resultat.
- El token efímer viu 60 s, és d'un sol ús i queda lligat al recurs exacte.
- `system.heartbeat` no toca cap servei extern.

## UI

Cap (el component `JobProgress` arriba amb les primeres pantalles de sync de la Fase 1).

## Fora d'abast

- Reintents amb backoff i dead-letter queue: arriben amb els primers jobs reals de la Fase 1 (backlog B-009).
- `POST /sync-runs` i tipus de job de negoci.
- `purpose=download` del token efímer (amb les exportacions).

## Criteris d'acceptació

- [x] El runner deixa la fila `jobs` amb les transicions i timestamps correctes en èxit, error i cancel·lació.
- [x] `dedup_key` impedeix un segon job viu idèntic.
- [x] El creador veu el seu job; un altre `employee` rep `403`; un admin el veu.
- [x] El token efímer només funciona una vegada i només per al seu recurs.
- [x] SSE emet l'estat inicial i els esdeveniments publicats, i talla en estat terminal.
- [x] Dos schedulers simultanis: només un té el lock.
- [x] Contracte validat (Redocly), client TS regenerat, bateries backend i frontend verdes.
