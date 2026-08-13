# Service accounts / API keys (Estat: implementada — fase 1)

## Context i objectiu

Fase 2 ([05-api.md](../docs/05-api.md) §1: «API keys de servei (`Authorization: Bearer sk_...`) amb scopes granulars i caducitat»; [06-seguretat.md](../docs/06-seguretat.md) §3: «passen pel mateix motor amb els seus scopes; mai personifiquen usuaris»). Identitat de màquina per a n8n, integracions i els futurs agents d'IA.

## Comportament

### Model (migració 0013)

- `service_accounts`: `name`, `description`, `key_prefix` (12 primers caràcters, per identificar sense revelar), `key_hash` (SHA-256 de la clau — la clau **mai** es desa), `scopes TEXT[]` (accions de la matriu A2), `active`, `expires_at NULL`, `last_used_at`, `created_by`.

### Autenticació i autorització

- `Authorization: Bearer sk_...` es resol a la mateixa dependència d'autenticació: hash → compte actiu i no caducat → identitat de màquina; es registra `last_used_at`.
- `Authorize(acció)` per a màquines: **l'acció ha de ser als scopes** de la clau; concedeix accés ALL (les màquines no tenen departament — la granularitat és l'scope, no l'abast). El paràmetre `?view` s'ignora per a màquines: l'abast efectiu és sempre global. Denegació → 403 auditada amb `actor_type: agent`.
- > ⚠️ **Fase 1**: les màquines accedeixen als endpoints protegits amb `Authorize(...)` (lectura de contractes/menors/adjudicataris/tasques, stats, facets, exports...). Els endpoints d'escriptura que usen la sessió d'usuari directament (PATCH, accions, tasques) responen 401 a una API key — la identitat de màquina completa per a escriptures és la fase 2 (anotat a BACKLOG B-013).
- Rate limiting: les claus comparteixen els límits per identitat existents (la clau és la identitat).

### Gestió (`service_accounts:manage`, només admin — mateixa fila d'A2 que la configuració)

- `GET /service-accounts` (mai la clau; prefix + last_used_at), `POST` (nom, scopes, caducitat opcional) — **la clau es mostra NOMÉS a la resposta de creació**; `PATCH` (activa/desactiva, scopes); `DELETE` (revocació immediata).
- Els scopes vàlids són les accions de la matriu A2 (es validen contra la matriu).
- Auditoria: `service_accounts.create/update/delete` i `authz.denied` amb tipus agent.

### UI

- **/admin/service-accounts**: mateixa pauta que webhooks — alta amb clau visible un sol cop i copiable, llista amb prefix/scopes/caducitat/últim ús, activar/desactivar, revocar amb confirmació.

## Canvis d'API

`openapi.yaml`: recurs `service-accounts` (tag nou). Client TS regenerat.

## Canvis de dades

Migració 0013.

## Seguretat

- La clau: `sk_` + 43 caràcters aleatoris (256 bits); a BD només SHA-256. Es mostra una única vegada.
- Sense clau vàlida → 401 idèntic al d'un JWT invàlid (cap oracle).
- Mai personifiquen usuaris: l'auditoria les registra com a `agent`, amb el seu id propi.

## Criteris d'acceptació

- [x] Una clau amb scope `contracts:read` llegeix contractes; sense l'scope → 403 auditat; caducada o revocada → 401.
- [x] Endpoints d'escriptura amb sessió d'usuari → 401 per a claus (fase 1, documentat).
- [x] Clau només visible en crear; a BD només el hash.
- [x] UI completa; bateries verdes.
