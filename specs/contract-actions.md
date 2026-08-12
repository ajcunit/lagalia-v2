# Accions de contracte i alertes de venciment (Estat: implementada)

## Context i objectiu

Tercera part de la F1-7 ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.4 i §2.8): les accions manuals sobre un contracte (finalitzar, descartar l'alerta, enriquir), l'assignació massiva de departaments i el job `alerts.recompute` que calcula les alertes de venciment que fins ara ningú no omplia.

## Comportament

Regles verificables (permisos segons [A2](../docs/annexos/A2-matriu-permisos.md) §2):

### Alertes (`alerts.recompute`)

- Per a cada contracte amb `calculated_end_date` i estat actual viu — s'exclouen «Finalitzat» i els estats morts reals de la font: «Anul·lació», «Desert», «Desistiment», «Renúncia» ([02] §5.170; valors verificats a BD amb dades reals):
  - `possibly_finished` = `calculated_end_date < avui`;
  - `expiry_warning` = `avui ≤ calculated_end_date ≤ avui + finestra`, on finestra (mesos) = `warning_months_override` del contracte o el paràmetre global `contracts.expiry_warning_months` (taula `settings`, defecte **6**).
- **Descart persistent**: si l'usuari ha descartat l'alerta (`alert_dismissed_end_date == calculated_end_date`), cap de les dues alertes no es torna a aixecar. Si la data final canvia (pròrroga, resincronització), el descart deixa de tenir efecte.
- Els contractes finalitzats/anul·lats i els que no compleixen les condicions queden amb les dues alertes a `false`.
- El job és seqüencial i idempotent; s'executa sota demanda (l'encadenament al scheduler i post-sync s'anotarà quan hi hagi cadència acordada).

### Accions individuals (subrecursos POST, fora d'abast → 404)

- `POST /contracts/{id}/actions/finish` — permís `contracts:close_alert` (admin, resp. contractació; responsable **només si n'és responsable del contracte**, mai per simple pertinença departamental). Posa `status = "Finalitzat"`, neteja les dues alertes, historial (`change_type: manual`, camp `status`) i auditoria `contracts.finish`. Si ja està finalitzat → 409.
- `POST /contracts/{id}/actions/dismiss-expiry` — mateix permís. Registra `alert_dismissed_at` + `alert_dismissed_end_date = calculated_end_date` i neteja les dues alertes; historial + auditoria `contracts.dismiss_expiry`. Si no hi ha cap alerta activa → 409.
- `POST /contracts/{id}/actions/enrich` — permís `contracts:enrich` (admin, resp. contractació). **No crida el portal dins la request**: encua `enrich.contract` (`force: true`) i respon 202 amb el job. Si el connector `pscp` està desactivat → 409 `connector-disabled` a l'encuament.
- Obrir a Gestiona queda per a la Fase 2 (hub Gestiona, B-001/B-002).

### Assignació massiva

- `POST /contracts/bulk/assign-departments` — permís `contracts:bulk_assign` (admin, resp. contractació). Cos: `contract_ids` (1–500), `department_ids` (1–20), `mode` `add`|`replace`. Valida que tots els departaments existeixin (422 si no); els ids de contracte inexistents s'ignoren i es reporten. Historial per contracte modificat (camp `departments`) i **una** entrada d'auditoria `contracts.bulk_assign` amb els comptadors.

## Canvis d'API

`openapi.yaml`: rutes `POST /contracts/{id}/actions/{finish|dismiss-expiry|enrich}`, `POST /contracts/bulk/assign-departments`; esquema `BulkAssignRequest`/`BulkAssignResult`. Les accions d'estat retornen el `ContractDetail` actualitzat; enrich retorna el `Job` (202).

## Canvis de dades

Migració `0009`: `contracts.alert_dismissed_at` (timestamptz) i `contracts.alert_dismissed_end_date` (date).

## Seguretat i permisos

- Cap crida externa dins de requests: enriquiment via cua de jobs.
- Accions fora d'abast → 404 (anti-IDOR); denegacions per permís → 403 auditades (`authz.denied`).
- Tota escriptura deixa historial de contracte i rastre a `audit_log`.

## UI (fitxa i llistat)

- Fitxa: banner vermell si `possibly_finished` (accions *Finalitzar* i *Descartar l'alerta*, amb confirmació) i groc si `expiry_warning` (acció *Descartar l'alerta*); botó *Enriquir* (si el rol pot) que encua el job i **en segueix l'estat** (sondeig de `GET /jobs/{id}` fins a estat terminal): èxit → refresc automàtic de la fitxa; fallada → l'error del job visible en un banner (B-012; la versió SSE queda anotada al backlog).
- Llistat: selecció múltiple amb caselles i barra flotant amb *Assigna departaments* (selector + add/replace), només per a rols amb `contracts:bulk_assign`.

## Fora d'abast

- Obrir a Gestiona (Fase 2), exports CSV/XLSX i stats/facets (F1-7d).
- Cadència automàtica d'`alerts.recompute` (scheduler) i encadenament post-sync.

## Criteris d'acceptació

- [x] `alerts.recompute` aixeca i neteja alertes segons les regles, respecta el descart mentre la data final no canviï.
- [x] finish/dismiss per rol: responsable del contracte sí, responsable del departament no, employee no (403); fora d'abast 404.
- [x] enrich encua el job i falla 409 amb el connector desactivat.
- [x] bulk assign add/replace amb historial i auditoria; department inexistent 422.
- [x] UI: banners amb accions i assignació massiva funcionals.
- [x] Bateries verdes; client TS regenerat.
