# Auditoria de seguretat: consulta i verificacio (Estat: implementada)

## Context i objectiu

`audit_log` es append-only amb cadena de hash ([04-model-de-dades.md](../docs/04-model-de-dades.md) §9) pero nomes es podia consultar per BD. API de consulta + pantalla `/admin/audit-log` (entrada de menu «Auditoria de seguretat» ja existent) + verificacio d'integritat de la cadena ([06-seguretat.md](../docs/06-seguretat.md): immutabilitat verificable).

## Comportament

### API (accio `audit_log:read`, nomes admin segons A2)

- `GET /audit-log` — paginacio keyset per `id` desc (immutable i monoton; `page[size]` fins a 200, `page[cursor]` opac). Filtres AND: `filter[action]` (prefix, p. ex. `auth.`), `filter[actor_type]`, `filter[actor_id]`, `filter[success]`, `filter[resource_type]`, `filter[resource_id]`, `filter[trace_id]`, `filter[from]`/`filter[to]` (interval de `occurred_at`). Resposta: entrades completes (sense `user_agent` truncat) + `actor_name` resolt per a actors usuari (LEFT JOIN; una maquina o un actor esborrat surt sense nom). `details` es retorna tal qual: mai conte cossos de peticio (06 §2) ni secrets, per construccio de `record_audit`.
- `POST /audit-log/actions/verify` — recorre la cadena sencera per `id` asc i comprova (1) enllaç `prev_hash == entry_hash` de l'anterior i (2) recomputa `entry_hash = sha256(prev_hash || payload canonic)` de cada entrada. Retorna `{status: ok|broken, checked, first_broken_id?, detail?}`. La primera fila present fa d'ancora (les entrades anteriors a la instal·lacio del trigger poden no existir). Operacio de nomes lectura; s'audita l'execucio (`audit.verify_chain`).

### Pantalla /admin/audit-log

- Taula: quan, actor (nom o `tipus#id`), accio, recurs, exit (badge), IP, traça; `details` desplegable per fila (JSON formatat).
- Filtres: accio (prefix), tipus d'actor, exit, interval de dates; «Carrega'n mes» amb el cursor.
- Boto «Verifica la integritat» (amb el resultat visible: ok + entrades comprovades, o trencada a #id).
- Consulta pura: cap escriptura des de la pantalla (la taula es immutable).

## Canvis d'API

`GET /audit-log`, `POST /audit-log/actions/verify` (tag `audit`). Cap canvi de dades.

## Seguretat

- Nomes admin (`audit_log:read`); tota denegacio queda auditada pel motor.
- La verificacio no exposa hashos parcials manipulables: nomes id i estat.

## Fora d'abast

- Export CSV de l'auditoria; retencio/arxivat; alertes automatiques sobre patrons (backlog).

## Criteris d'acceptacio

- [x] Admin llista i filtra; no-admin → 403 auditat.
- [x] Verificacio retorna `ok` sobre la BD real; una manipulacio simulada es detecta.
- [x] Pantalla amb filtres, detalls i verificacio.
- [x] Bateries verdes.
