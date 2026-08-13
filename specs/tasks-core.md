# Tasques i recordatoris de contracte — nucli (Estat: implementada)

## Context i objectiu

Primera peça de la Fase 2 i primer mòdul **nou** de la v2 ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.19, [04-model-de-dades.md](../docs/04-model-de-dades.md) §4bis, [05-api.md](../docs/05-api.md)): els responsables calendaritzen tasques sobre els seus expedients i les alertes passives esdevenen accionables. Aquesta PR és el nucli (model + API); la UI (calendari, pestanya de la fitxa, widget, iCal) i el lliurament de recordatoris (job + canals email/webhook) vénen a les següents.

## Comportament

### Model (migració 0010, segons 04 §4bis)

- `tasks`: títol, descripció, `task_type` (`review|extension|settlement|guarantee_return|report|meeting|other`), `due_date` (+`due_time` opcional), `priority` (`low|normal|high`), `status` (`pending|in_progress|done|cancelled`), contracte **o** menor associat (CHECK: com a mínim un), departament opcional, `recurrence` (RRULE), `parent_task_id` per a ocurrències generades, `created_by`, `completed_by/completed_at`, `resolution_notes`.
- `task_assignees` (M2M usuaris), `task_reminders` (offset_days + canal + sent_at, definició i registre en una fila per ocurrència), `task_history` (canvi per canvi).
- > ⚠️ DESVIACIÓ de 04 §4bis: `plan_entry_id` s'ometrà fins que existeixi el pla anual (Fase 2, PR posterior); s'afegirà amb la seva migració.

### Permisos (A2 §2, Tasques)

- **Veure**: admin/resp. contractació tot; responsable ✔ᴰ (tasques de contractes del seu abast o creades per ell); employee només les **assignades** a ell.
- **Crear/editar/esborrar**: admin/pm sobre qualsevol; responsable ✔ᴰ sobre contractes del seu abast; employee no.
- **Canviar l'estat** (complete/cancel/reopen): qualsevol **assignat**, a més dels qui poden editar.
- Fora d'abast → 404; sense permís → 403 auditat.

### API

- `GET /tasks` — filtres `status`, `due_before`, `due_after`, `contract_id`, `minor_contract_id`, `assignee_id`, `department_id`; ordenació per venciment; paginació per cursor. `GET /tasks/calendar?from=&to=[&department_id=]` — les tasques del rang (mateix abast), pensat per a la vista calendari.
- `POST /tasks` — amb `assignee_ids[]`, `reminders[]` (offset_days + canal) i `recurrence` opcional (RRULE; es valida). El contracte/menor associat ha de ser dins l'abast del creador.
- `GET/PATCH/DELETE /tasks/{id}` — el PATCH registra cada canvi a `task_history`.
- `POST /tasks/{id}/actions/complete|cancel|reopen` — assignats o editors; `complete` amb `resolution_notes` opcional. **Recurrència**: en completar una tasca amb RRULE es genera la següent ocurrència (mateixos assignats i recordatoris pendents, `parent_task_id` a l'original).
- `GET /contracts/{id}/tasks` i `GET /minor-contracts/{id}/tasks` — pestanya de la fitxa (abast del contracte).
- `GET /tasks/suggestions` — proposades des de les alertes existents, dins l'abast: contracte amb `expiry_warning` → «Tramitar pròrroga / revisar venciment abans de {data final}» (tipus `extension`); `possibly_finished` → «Revisar finalització i liquidació» (tipus `settlement`). Es dedupliquen per **expedient** (els lots germans comparteixen `file_code`: una sola proposta, amb la data final més primerenca) i s'exclouen els expedients amb una tasca oberta del mateix tipus sobre qualsevol dels seus lots. **Acceptar** = crear la tasca amb `POST /tasks`; **descartar** l'alerta ja existeix (`dismiss-expiry`).
- Tota escriptura deixa `task_history` i `audit_log` (`tasks.create/update/delete/status`).

## Canvis d'API

`openapi.yaml`: recurs `tasks` complet (tag nou). Client TS regenerat.

## Canvis de dades

Migració 0010 (quatre taules noves + enums).

## Fora d'abast

- Lliurament de recordatoris (job `tasks.reminders` + canals email/webhook — arriba amb el connector SMTP i els webhooks sortints; les definicions ja es desen).
- UI (calendari, pestanya, widget dashboard) i feed iCal — PR següent.
- `plan_entry_id` (amb el pla anual).

## Criteris d'acceptació

- [x] CRUD amb permisos per rol testats (admin/pm/responsable ✔ᴰ/employee assignat).
- [x] Completar una tasca recurrent genera la següent ocurrència amb assignats i recordatoris.
- [x] Suggeriments derivats de les alertes, dins d'abast i sense duplicar tasques obertes.
- [x] Historial per canvi i auditoria per escriptura.
- [x] Bateries verdes; client TS regenerat.
