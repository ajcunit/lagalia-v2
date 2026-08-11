# Motor d'autorització (Estat: implementada)

## Context i objectiu

Quarta PR de la Fase 0 ([00-primers-passos.md](../docs/00-primers-passos.md) §4): el fonament de tota la resta. Implementa el motor central d'autorització de [06-seguretat.md](../docs/06-seguretat.md) §3 amb la matriu de l'annex [A2](../docs/annexos/A2-matriu-permisos.md) com a única font de veritat, la dependency `Authorize(action)` i `GET /me/permissions`.

## Comportament

Donat un usuari autenticat,
Quan un endpoint declara `Authorize("recurs:acció")`,
Aleshores la petició només prossegueix si la matriu A2 concedeix l'acció al rol (i als flags) de l'usuari; qualsevol denegació retorna `403` Problem i queda registrada a `audit_log`.

Regles verificables:

- **La matriu A2 viu com a dades** (`app/core/authz.py`, `PERMISSION_MATRIX`): accions en format `recurs:acció`, i per a cada rol un `Grant` amb tipus d'accés i flag opcional. El codi del motor no té cap coneixement de rols concrets fora de la matriu.
- **Tipus d'accés** (`Access`): `ALL` (sense restricció), `DEPT` (abast departamental de §3 de l'A2), `MANAGED` (només recursos dels quals és responsable), `ASSIGNED` (només recursos assignats a l'usuari). `MANAGED`/`ASSIGNED` es materialitzen als resource loaders de cada mòdul (Fase 1); el motor ja els distingeix.
- **Flags**: `can_audit` i `can_plan` condicionen les accions que l'A2 marca; sense el flag, l'acció no apareix ni s'autoritza.
- **Cap check de rol als routers**: només `Authorize(action)` com a dependency. El lint de seguretat de CI ho vigila.
- **Denegacions auditades** (`authz.denied`) amb actor, acció i recurs (regla 4 de l'A2).
- **Abast** (`scope_for`): `admin`/`procurement_manager` → `all`; `dept_manager`/`employee` → `departments` amb els seus ids. Sense departaments → llista buida (mai «tot»).
- **Vista Admin/Usuari**: `resolve_view_scope(user, view)` valida el paràmetre `view=all|user` contra el rol real (mai capçalera de confiança). `view=all` sense permís → `403` auditat.
- **`GET /me/permissions`**: retorna `role`, `actions` (les concedides pel rol i flags, ordenades), `scope` i `can_switch_view`, conforme al contracte. La UI no dedueix mai permisos del rol.
- **Divergència v1→v2 mantinguda**: `users:read`/`users:write` només admin (A2 §2 ⚠️; el backlog en recull la validació amb l'organització).

## Canvis d'API

Cap canvi de contracte: implementa `GET /me/permissions` tal com és a [openapi.yaml](../openapi.yaml).

## Canvis de dades

Cap migració. Es llegeixen `users`, `user_departments` i s'escriu `audit_log`.

## Seguretat i permisos

- El motor és l'únic camí d'autorització; els scopes de service accounts (Fase 1+) es mapegen sobre aquestes mateixes accions.
- Interpretacions fixades on l'A2 és ambigua (revisables amb l'organització):
  - `system:read` (readiness): només admin.
  - `departments:read`: tots els rols (les referències de departament apareixen a tota la UI); `departments:write`: admin i procurement_manager.
  - Pla anual, veure: `dept_manager` per abast departamental sense flag; `employee` requereix `can_plan`.
  - `tasks:update_status`: admin/procurement_manager sobre qualsevol tasca; dept_manager/employee només assignades.

## UI

Cap (el sidebar per permisos arriba amb la PR #8 consumint `/me/permissions`).

## Fora d'abast

- Resource loaders amb filtre departamental per a contractes/menors/tasques (Fase 1, quan existeixin els recursos); `MANAGED`/`ASSIGNED` efectius als detalls.
- Service accounts i API keys (`sk_...`).
- OIDC.

## Criteris d'acceptació

- [x] Test parametritzat **rol × acció × abast** transcrit de l'A2 independentment de la matriu del codi (taula de veritat).
- [x] `GET /me/permissions` per a cada rol retorna accions i abast coherents amb l'A2.
- [x] Una petició denegada retorna `403` Problem i crea entrada `authz.denied` a `audit_log`.
- [x] `view=all` demanat per un `employee` → `403`; per un `admin` → abast complet.
- [x] Usuari sense departaments amb rol departamental → `scope.department_ids == []`.
- [x] `ruff`, `mypy --strict` i tota la suite verds.
