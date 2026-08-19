# Retenció i purga de dades (Estat: implementada)

## Context i objectiu

B-006 i 06-seguretat §7: l'auditoria i les entrades/sortides d'IA són
dades personals i no es poden guardar per sempre. Valors per defecte
acceptats per l'Esteve (2026-08-19), **configurables segons les
indicacions del DPO** sense desplegar.

## Comportament

- Job `retention.purge`, programat **diari** (SCHEDULE fixa), esborra:
  - `audit_log` amb `occurred_at` anterior a `retention.audit_log_days`
    (per defecte **730 dies** = 2 anys);
  - `ai_runs` i les converses de xat (`chat_messages` vells i
    `chat_threads` que queden buits) anteriors a `retention.ai_days`
    (per defecte **365 dies** = 1 any).
- Terminis als settings `retention.audit_log_days` i `retention.ai_days`
  (pantalla Paràmetres), acotats a **30–3650 dies**: un valor invàlid o
  fora de rang cau al per defecte — un error de configuració mai buida
  l'auditoria.
- La purga deixa rastre: entrada `retention.purge` (actor `system`) via
  `record_audit` amb els comptadors i els terminis aplicats — mai un
  INSERT cru, que trencaria la cadena de hashos.
- **Append-only amb porta sancionada** (migració 0034): `audit_log` manté
  el trigger que bloca UPDATE/DELETE; només la transacció de la purga
  (marca `SET LOCAL app.retention_purge = 'on'`) pot esborrar, i el
  trigger a més exigeix files de **>30 dies** (ni la purga pot esborrar
  auditoria fresca).
- **Cadena de hashos**: la purga només esborra el **prefix** de la cadena
  (files caducades sense cap entrada posterior per id) — una fila del mig
  trencaria l'enllaç `prev_hash` de la següent. El verificador
  (`audit-log/actions/verify`) ancora la primera entrada disponible tal
  qual, així que el truncament del començament sempre verifica.

## Canvis d'API

Cap: settings existents (`GET/PUT /settings`) i job visible a la safata.

## Fora d'abast

- Retenció de documents descarregats i generats (política municipal de
  còpies, B-003) i de `sync_runs`/`jobs` (operacionals, no personals).

## Criteris d'acceptació

- [x] Purga diària amb terminis configurables i acotats.
- [x] Les dades dins del termini no es toquen; les caducades desapareixen.
- [x] Rastre d'auditoria de cada purga; cadena de hashos verificable.
- [x] Bateries verdes.
