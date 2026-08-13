# Connector SMTP i lliurament de recordatoris (Estat: implementada)

## Context i objectiu

Tanca el mòdul de tasques ([tasks-core.md](tasks-core.md) ho deixava fora d'abast; [04-model-de-dades.md](../docs/04-model-de-dades.md) §4bis: job diari `tasks.reminders`): les definicions de recordatori que ja es desen amb cada tasca ara **s'envien** — per email (connector `smtp`) i/o per webhook (esdeveniments cap a n8n → Teams/Telegram).

## Comportament

### Connector `smtp` (hub, desactivat per defecte)

- Manifest: config `host`, `port` (587), `starttls` (cert), `from_address`, `from_name`; credencials `username`, `password` (xifrades pel hub com totes).
- Enviament amb `smtplib` de la stdlib **en thread** (cap crida bloquejant a l'event loop); TLS sempre verificat.
- Healthcheck: connexió + EHLO (+ STARTTLS si toca), sense enviar res.

### Job `tasks.reminders` (scheduler, horari; idempotent)

- **Recordatoris vençuts no enviats**: `task_reminders.sent_at IS NULL` de tasques obertes amb `due_date - offset_days <= avui`:
  - canal `email` → correu en català als assignats (títol, expedient, venciment). **Si el connector smtp està desactivat o sense assignats amb correu, queda pendent** (s'enviarà quan s'activi; el job ho reporta).
  - canal `webhook` → esdeveniment `task.due_soon` a l'outbox (el consumeixen els webhooks subscrits).
  - En èxit es marca `sent_at` (definició i registre en una fila, com mana 04 §4bis).
- **Reavís de vençudes**: tasques obertes amb `due_date < avui` → esdeveniment `task.overdue` + email als assignats, **com a molt un cop al dia per tasca** (clau de deduplicació diària a Redis; si Redis es buida, el pitjor cas és un reavís extra).
- En acabar, encua el despatxador de webhooks.

## Canvis d'API

Cap (el connector es gestiona amb l'API de connectors existent; els esdeveniments nous ja encaixen al contracte d'esdeveniments de 05 §4).

## Canvis de dades

Cap migració.

## Seguretat

- Credencials SMTP xifrades (AES-256-GCM) via `connector_credentials`; mai en respostes ni logs.
- Els correus no contenen dades més enllà del que veu l'assignat a l'app; TLS verificat sempre.

## Fora d'abast

- Plantilles HTML d'email (text pla, suficient i accessible); digest setmanal.
- UI de configuració del connector (pantalla de configuració, pendent).

## Criteris d'acceptació

- [x] Recordatori email enviat quan venç l'offset i marcat `sent_at`; sense connector actiu queda pendent i reportat.
- [x] Recordatori webhook emet `task.due_soon` a l'outbox.
- [x] Vençudes: `task.overdue` + email amb dedupe diari.
- [x] Bateries verdes.
