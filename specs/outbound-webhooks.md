# Webhooks sortints amb outbox transaccional (Estat: implementada)

## Context i objectiu

Fase 2 ([05-api.md](../docs/05-api.md) §4, [04-model-de-dades.md](../docs/04-model-de-dades.md) §8): la v2 emet esdeveniments de negoci que integracions externes (n8n → Teams/Telegram, futurs subscriptors interns) consumeixen per webhook signat. És el prerequisit del lliurament de recordatoris de tasques i del pont Gestiona.

## Comportament

### Outbox transaccional (`outbox_events`)

- `emit_event(session, type, aggregate, aggregate_id, data)` escriu l'esdeveniment **a la mateixa transacció** que l'escriptura de negoci: mai es publica un fet que després es reverteix, mai es perd un fet comès.
- Format CloudEvents JSON: `{id, source: "lagalia", type, time, subject: "{aggregate}/{id}", data}`.
- Emissors cablejats en aquesta PR: `contract.finished` (acció finalitzar), `contractor.merged` (toda fusió, individual/grup/consolidació), `sync.completed`/`sync.failed` (fi de run) i `task.completed`. La resta del catàleg de 05 §4 s'anirà cablejant amb cada mòdul (anotat; `contract.created/updated` per sync es descarta de moment: inundaria — es reconsiderarà amb filtres).

### Despatxament (`webhooks.dispatch`)

- Job seqüencial: (1) publica els esdeveniments pendents de l'outbox creant una **delivery** per webhook actiu subscrit (coincidència exacta del tipus o `*`); (2) envia les deliveries vençudes.
- Enviament: POST JSON amb `X-Webhook-Id`, `X-Timestamp` (unix) i `X-Signature: sha256=hex(HMAC_SHA256(secret, "{timestamp}.{cos}"))` — el receptor verifica signatura i finestra de temps (anti-replay). Timeout 10 s.
- Reintents exponencials: `next_retry_at = ara + 30s·2^intents`, fins a **8 intents**; després `failed` definitiu amb `last_error`.
- `emit_event` encua el dispatch (dedup: un de sol en cua); el **scheduler** el llança també cada 5 minuts per als reintents pendents.

### API (`webhooks:manage`, **només admin** — mateixa fila que «escriure configuració» d'A2)

- `GET /webhooks`, `POST /webhooks` (nom, url httpS, events[]) — el **secret es genera al servidor, es desa xifrat (AES-256-GCM) i es mostra NOMÉS a la resposta de creació** (`is_set: true` després, regla de secrets de 06 §2).
- `DELETE /webhooks/{id}`; `PATCH` per activar/desactivar i canviar events.
- `GET /webhooks/{id}/deliveries` — històric amb estat, intents i últim error.
- `POST /webhooks/{id}/actions/test` — encua un esdeveniment `webhook.test` només per a aquest webhook (verificació d'extrem).
- Auditoria: `webhooks.create/update/delete/test`.

### Seguretat

- URL de destí: només `https://` (o `http://` cap a hosts privats explícitament en desenvolupament); el secret mai apareix en respostes ni logs (06 §2).
- El payload no inclou mai secrets ni dades personals més enllà del que ja exposa l'API del recurs.
- Cap enviament dins de requests d'usuari: tot via cua de jobs (prohibició de 06 §2).

## Canvis d'API

`openapi.yaml`: recurs `webhooks` complet (tag nou). Client TS regenerat. (La UI d'administració de webhooks arribarà amb la pantalla de configuració; mentrestant, Swagger.)

## Canvis de dades

Migració 0012: `outbox_events`, `outbound_webhooks`, `webhook_deliveries`.

## Fora d'abast

- Service accounts / API keys (PR següent — 05 §1).
- Canal email (connector SMTP) i el job `tasks.reminders` que consumirà aquests canals.
- UI d'administració de webhooks.

## Criteris d'acceptació

- [x] emit_event a la mateixa transacció; dispatch crea deliveries només per a subscriptors del tipus.
- [x] Signatura HMAC verificable i timestamp; reintents amb backoff i fallada definitiva al 8è intent.
- [x] Secret només visible en crear; xifrat a BD; mai a GET.
- [x] Acció de test end-to-end; deliveries consultables.
- [x] Esdeveniments reals: finalitzar contracte, fusió d'adjudicataris, fi de sync, tasca completada.
- [x] Bateries verdes.
