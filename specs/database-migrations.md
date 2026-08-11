# Base de dades i migracions (Estat: implementada)

## Context i objectiu

Segona PR de la Fase 0 ([00-primers-passos.md](../docs/00-primers-passos.md) §4). Estableix la capa de persistència: SQLAlchemy 2 async, Alembic com a únic mecanisme d'evolució de l'esquema, i la migració inicial amb les taules d'organització, sessions i auditoria de [04-model-de-dades.md](../docs/04-model-de-dades.md) §3 i §9.

## Comportament

Donat un PostgreSQL 16 buit (amb o sense les extensions de `ops/db-init`),
Quan s'executa `alembic upgrade head`,
Aleshores es creen les taules `departments`, `users`, `user_departments`, `refresh_tokens` i `audit_log` amb les seves restriccions, índexs i triggers, de manera idempotent i reversible (`alembic downgrade base` les elimina).

Regles verificables:

- Convencions de [04-model-de-dades.md](../docs/04-model-de-dades.md): PK `BIGINT GENERATED ALWAYS AS IDENTITY`, `created_at`/`updated_at` amb trigger, FK amb `ON DELETE` explícit, noms en anglès `snake_case`.
- `users.email` és `CITEXT UNIQUE` (insensible a majúscules). La migració crea l'extensió `citext` de forma idempotent perquè la CI no executa `ops/db-init`.
- `users.role` és l'enum PostgreSQL `user_role` amb els mateixos valors que `Role` d'[openapi.yaml](../openapi.yaml): `admin | procurement_manager | dept_manager | employee`.
- El DNI es guarda **xifrat** (`dni_encrypted BYTEA NULL`), mai en clar ([06-seguretat.md](../docs/06-seguretat.md) §4). El xifrat aplicatiu arriba amb el CRUD d'usuaris; aquí només el tipus de columna.
- `auth_source` de l'API no és cap columna: es deriva de `password_hash` (`NULL` → `ldap`).
- `refresh_tokens`: `token_hash UNIQUE`, `family_id UUID` per a detecció de reutilització, `revoked_at`, `created_ip INET`; FK a `users` amb `ON DELETE CASCADE`.
- `audit_log` és **append-only**: un trigger rebutja `UPDATE` i `DELETE`. Cadena d'immutabilitat amb `prev_hash`/`entry_hash`. En producció cal, a més, revocar UPDATE/DELETE al rol d'aplicació (nota d'operacions).
- `user_departments` només té `created_at`: una assignació no es modifica, es crea i s'esborra.
- La sessió async s'obté d'`app/core/db.py` (engine únic, `expire_on_commit=False`); cap `CREATE TABLE` fora d'Alembic.

## Canvis d'API

Cap. `/health/ready` continua fora d'abast (necessita també redis i storage; arribarà amb la cua de treballs).

## Canvis de dades

Migració `0001_initial_schema`:

| Taula | Contingut |
|---|---|
| `departments` | `code UNIQUE`, `name`, `description`, `active`, `gestiona_group_id/name/href` |
| `users` | `name`, `email CITEXT UNIQUE`, `role user_role`, `active`, `password_hash NULL`, `dni_encrypted BYTEA NULL`, `can_audit`, `can_plan` |
| `user_departments` | M2M amb PK composta i `ON DELETE CASCADE` als dos costats |
| `refresh_tokens` | `token_hash UNIQUE`, `user_id FK CASCADE`, `family_id UUID`, `expires_at`, `revoked_at NULL`, `created_ip INET` |
| `audit_log` | `occurred_at`, `actor_type user\|agent\|system`, `actor_id NULL`, `action`, `resource_type`, `resource_id`, `ip INET`, `user_agent`, `trace_id`, `details JSONB`, `success`, `prev_hash`, `entry_hash` |

Funcions/triggers: `set_updated_at()` (a `departments`, `users`, `refresh_tokens`) i `audit_log_block_mutation()` (append-only).

Índexs: `refresh_tokens(user_id)`, `refresh_tokens(family_id)`, `audit_log(occurred_at)`, `audit_log(actor_id)`, `audit_log(action)`, `user_departments(department_id)`.

## Seguretat i permisos

Cap endpoint nou. El DNI mai en clar; `audit_log` immutable per trigger; els tokens de refresc es guarden com a hash, mai el valor.

## UI

Cap.

## Fora d'abast

- Xifrat aplicatiu del DNI i `user_credentials` (PR d'usuaris).
- Emissió i rotació de refresh tokens (PR d'autenticació).
- Escriptura d'entrades a `audit_log` des de l'aplicació (PR d'autenticació).
- Resta de taules del model (nucli de contractació, jobs, IA…): arriben amb les seves fases.

## Criteris d'acceptació

- [x] `alembic upgrade head` funciona sobre una BD buida sense `ops/db-init` (cas CI).
- [x] `alembic downgrade base` deixa la BD neta.
- [x] Test d'integració: les cinc taules existeixen amb les columnes esperades.
- [x] Test d'integració: `UPDATE`/`DELETE` sobre `audit_log` fallen.
- [x] Test d'integració: `updated_at` canvia automàticament en fer `UPDATE`.
- [x] Test d'integració: `users.email` rebutja duplicats que només difereixen en majúscules.
- [x] `ruff`, `mypy --strict` i tota la suite verds.
