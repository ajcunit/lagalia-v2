# Usuaris i departaments (Estat: implementada)

## Context i objectiu

Cinquena PR de la Fase 0 ([00-primers-passos.md](../docs/00-primers-passos.md) §4): CRUD complet dels dos recursos de l'`openapi.yaml` inicial, amb baixa lògica i revocació de sessions, més el perfil propi (`PATCH /me`). Tanca l'abast de la Fase 0 al backend juntament amb el setup (PR #6).

## Comportament

Donat un administrador autenticat,
Quan crea, consulta, modifica o desactiva usuaris i departaments,
Aleshores cada operació passa per `Authorize(action)`, respecta el contracte i queda auditada.

Regles verificables:

- **Usuaris** (`users:read` / `users:write`, només admin per la divergència A2):
  - `GET /users`: paginació per cursor (keyset sobre el camp d'ordre + id, `page[size]` 1–500, `meta.total` i `meta.next_cursor`), filtres `filter[active]`, `filter[role]`, `filter[department_id]`, ordre `name|-name|created_at|-created_at` (per defecte `name`).
  - `POST /users` → `201`; correu duplicat (case-insensitive) → `409` Problem. `password` absent = usuari de directori (LDAP); present, ha de passar la política.
  - `PATCH /users/{id}`: canvis parcials; `active=false` també **revoca totes les sessions** (mateixa garantia que DELETE); `department_ids` substitueix el conjunt.
  - `DELETE /users/{id}` → `204`: **baixa lògica** (mai esborrat físic) + revocació de totes les famílies de refresh tokens.
- **Departaments** (`departments:read` per a tothom, `departments:write` admin/procurement_manager):
  - CRUD homòleg; codi duplicat → `409`; `DELETE` = baixa lògica.
  - `GET /departments/{id}/users` retorna els usuaris del departament (ordenats per nom).
- **Perfil propi** (`PATCH /me`, acció `me:update`): només `name`, `dni` i `password`. El rol i el correu no són editables per l'usuari. Un usuari de directori no pot posar-se contrasenya local (`422`).
- **DNI xifrat**: AES-256-GCM amb `ENCRYPTION_KEY` (`app/core/crypto.py`, blob versionat `0x01‖nonce‖ct` per a rotació futura). A la BD només `dni_encrypted`; les respostes el retornen desxifrat només on el contracte l'inclou.
- **Política de contrasenyes** ([openapi.yaml](../openapi.yaml) `Password`): mínim 12, majúscula, minúscula i xifra, i rebuig d'una llista embeguda de contrasenyes filtrades habituals (dataset complet: backlog B-008). S'aplica a `POST /users`, `PATCH /users/{id}` i `PATCH /me`.
- **Auditoria**: `users.create|update|deactivate`, `departments.create|update|deactivate`, `me.update` — amb els **noms** dels camps canviats, mai els valors (dades personals).
- **`Idempotency-Key`**: el header s'accepta però encara no es persisteix (backlog B-007); el `409` per duplicat en cobreix el cas principal.

## Canvis d'API

Cap canvi de contracte: implementa `/users`, `/users/{id}`, `/departments`, `/departments/{id}`, `/departments/{id}/users` i `PATCH /me` tal com són a [openapi.yaml](../openapi.yaml).

## Canvis de dades

Cap migració: tot cap a les taules de la migració 0001.

## Seguretat i permisos

- Tot endpoint passa per `Authorize(...)`; les denegacions s'auditen (motor de la PR #4).
- El DNI mai en clar a la BD ni als logs; la contrasenya mai enlloc.
- La desactivació (PATCH o DELETE) tanca la porta immediatament: refresh impossible; l'accés JWT viu com a màxim `ACCESS_TOKEN_EXPIRE_MINUTES`.
- Errors de cursor o d'ordre invàlids → `422` Problem, sense eco del valor rebut.

## UI

Cap (la gestió arriba amb la Fase 0 de frontend).

## Fora d'abast

- Idempotència persistent del header `Idempotency-Key` (B-007).
- Dataset complet de credencials filtrades (B-008).
- LDAP: alta/sincronització d'usuaris de directori (Fase 2); aquí només es permet crear-los sense contrasenya.
- `user_credentials` (tokens Gestiona per usuari, Fase 2).

## Criteris d'acceptació

- [x] CRUD d'usuaris i departaments conforme al contracte (201/200/204, 404, 409, 422).
- [x] `DELETE /users/{id}` i `PATCH active=false`: el refresh token deixa de funcionar immediatament.
- [x] Paginació: amb `page[size]=2` i 3 recursos, `next_cursor` recupera la resta sense duplicats.
- [x] `employee` intentant `POST /users` → `403` auditat.
- [x] `PATCH /me` xifra el DNI (a la BD no hi és en clar) i permet canviar la contrasenya (el login nou funciona, el vell no).
- [x] Contrasenya feble o filtrada → `422`.
- [x] `ruff`, `mypy --strict` i tota la suite verds.
