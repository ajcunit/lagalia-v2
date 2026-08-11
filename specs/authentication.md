# Autenticació (Estat: implementada)

## Context i objectiu

Tercera PR de la Fase 0 ([00-primers-passos.md](../docs/00-primers-passos.md) §4). Implementa la sessió d'usuaris humans de [05-api.md](../docs/05-api.md) §2: login amb credencials locals, renovació amb rotació de refresh token i detecció de reutilització per famílies, logout i perfil propi. Tots els intents queden auditats a `audit_log` amb cadena de hash.

## Comportament

Donat un usuari actiu amb contrasenya local,
Quan envia `POST /auth/login` amb credencials vàlides,
Aleshores rep un `TokenPair` (JWT d'accés de 30 min + refresh token opac de 7 dies) i es registra `auth.login` amb èxit a l'auditoria.

Regles verificables:

- **Login** (`POST /auth/login`, públic, rate limited):
  - Credencials incorrectes o usuari inexistent → `401` Problem, auditat com a `auth.login` `success=false`. La resposta és idèntica en els dos casos i el cost de temps també (verificació contra un hash fictici quan l'usuari no existeix).
  - Usuari desactivat (amb credencials correctes) → `403` Problem «Compte desactivat», auditat.
  - Usuari LDAP (`password_hash IS NULL`) → `401` mentre el connector LDAP no existeixi (Fase 2).
  - Rate limit: **5/min per IP** i **20/h per compte** ([06-seguretat.md](../docs/06-seguretat.md) §5) → `429` amb `Retry-After`.
- **Contrasenyes**: Argon2id (argon2-cffi, paràmetres per defecte de la llibreria, revisables). Mai cap altra funció de hash.
- **JWT d'accés**: HS256 amb `SECRET_KEY`, claims `sub` (user id), `sid` (família de sessió), `type=access`, `iat`, `exp` (=`ACCESS_TOKEN_EXPIRE_MINUTES`). Cap dada personal dins del token.
- **Refresh** (`POST /auth/refresh`, públic):
  - El refresh token és opac (43 chars urlsafe); a la BD només el seu SHA-256.
  - Cada ús el revoca i n'emet un de nou **a la mateixa família** (`family_id`).
  - Reutilitzar un token ja rotat o revocat → es revoca **tota la família** i `401`; auditat com a `auth.refresh_reuse` (detecció de robatori).
  - Token caducat o desconegut → `401`, auditat `success=false`.
- **Logout** (`POST /auth/logout`, autenticat): revoca tota la família del `sid` del token d'accés → `204`, auditat.
- **`GET /me`** (autenticat): retorna l'esquema `User` del contracte, amb `auth_source` derivat de `password_hash` i `departments` com a `DepartmentRef[]`. Mai credencials.
- **Errors**: RFC 9457 `application/problem+json` amb `trace_id`; mai s'hi eco el cos de la petició. Els 401 porten `WWW-Authenticate: Bearer`.
- **Traçabilitat**: cada petició rep un `trace_id` (middleware) que apareix als logs estructurats, a les respostes d'error i a `audit_log.trace_id`.
- **Auditoria**: escriptura serialitzada (advisory lock) amb `entry_hash = sha256(prev_hash || payload canònic)`; cobreix `auth.login`, `auth.refresh`, `auth.refresh_reuse`, `auth.logout`.

## Canvis d'API

Cap canvi del contracte: implementa `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` i `GET /me` tal com són a [openapi.yaml](../openapi.yaml).

## Canvis de dades

Cap migració nova: usa `users`, `refresh_tokens` i `audit_log` de la migració 0001.

## Seguretat i permisos

- El rate limiter guarda comptadors a Redis (`INCR`+`EXPIRE`); si Redis no respon, **s'obre** (el login continua funcionant) i es registra l'error — la disponibilitat del login preval, la mitigació és a capa de proxy.
- Cap secret ni contrasenya a logs, respostes o auditoria (els `details` d'auditoria només porten el correu intentat).
- `POST /auth/logout` amb token invàlid → `401` (mai revela si la sessió existia).

## UI

Cap (la pantalla d'accés arriba amb la PR #8).

## Fora d'abast

- LDAP (`docs/08-hub-integracions.md`, Fase 2): el login és només local.
- `POST /auth/ephemeral` (arriba amb la cua de treballs i SSE, PR #9).
- `PATCH /me` i política de contrasenyes en escriptura (PR #5, usuaris).
- `GET /me/permissions` i motor d'autorització (PR #4).
- OIDC.

## Criteris d'acceptació

- [x] Login vàlid → `TokenPair` conforme al contracte; invàlid → `401` uniforme; desactivat → `403`.
- [x] Refresh rota el token; la reutilització revoca la família sencera.
- [x] Logout revoca la família; el refresh posterior falla.
- [x] `GET /me` amb token vàlid retorna l'usuari; sense token → `401` Problem.
- [x] 6è login en un minut des de la mateixa IP → `429` amb `Retry-After`.
- [x] Cada intent (èxit i error) crea una entrada a `audit_log` amb cadena de hash vàlida.
- [x] `ruff`, `mypy --strict` i tota la suite verds.
