# Login i shell de l'aplicació (Estat: implementada)

## Context i objectiu

Vuitena PR i última de la Fase 0 ([00-primers-passos.md](../docs/00-primers-passos.md) §4): pantalla d'accés, guard de sessió, shell amb sidebar per permisos i assistent de setup ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.1–2.2, [10-ui.md](../docs/10-ui.md) §3).

## Comportament

Donat un sistema inicialitzat i un usuari actiu,
Quan entra les credencials a la pantalla d'accés,
Aleshores obté sessió (refresh rotatiu), veu el shell amb la sidebar filtrada pels seus permisos efectius i pot tancar sessió.

Regles verificables:

- **Sessió**: el refresh token es persisteix (`localStorage`); el token d'accés viu **només en memòria**. En carregar l'app es restaura la sessió via `POST /auth/refresh` (rotació). Si l'API retorna `401` en una petició GET, el client refresca una vegada i reintenta; si el refresh falla, la sessió es tanca i es torna al login.
- **Guard de rutes**: les rutes privades redirigeixen a `/login` si no hi ha sessió, i a `/setup` si `needs_setup` és cert. `/login` i `/setup` redirigeixen cap a dins si no toquen.
- **Login**: formulari accessible (labels explícites, errors anunciats amb `aria-live`); els errors mostren el `title` humà del Problem i el `trace_id` copiable ([10-ui.md](../docs/10-ui.md) §5); el `429` mostra el temps d'espera. Mai es mostra ni es registra la contrasenya.
- **Sidebar per permisos**: es construeix amb **una sola crida** a `GET /me/permissions` per sessió (TanStack Query, `staleTime: Infinity`); les entrades porten l'acció requerida i es filtren per `actions` — la UI **no dedueix res del rol**. Zones segons [10-ui.md](../docs/10-ui.md) §3; les pantalles de fases futures mostren un estat «en construcció».
- **Assistent de setup** de 4 passos (benvinguda → admin amb indicador de força de contrasenya → organització opcional (nom, INE10) → confirmació), amb la política de contrasenyes del contracte replicada com a checklist en viu (`aria-live`); l'èxit porta al login. Els errors 403/422/429 del backend es mostren com a Problem.
- **Logout**: `POST /auth/logout` (revoca la família) + neteja local + redirecció al login.
- **Perfil visible**: el shell mostra nom i rol de l'usuari (de `GET /me`, una crida per sessió).

## Canvis d'API

Cap: consumeix `login`, `refreshSession`, `logout`, `getMe`, `getMyPermissions`, `getSetupStatus`, `initializeSystem` del contracte existent.

## Canvis de dades

Cap.

## Seguretat i permisos

- El token d'accés mai s'escriu a `localStorage` ni apareix a URLs.
- El reintent automàtic post-refresh només s'aplica a peticions sense cos (GET); les mutacions fallides es reintenten per acció de l'usuari.
- La checklist de contrasenya és UX: la validació autoritativa és el backend.

## UI

Login, wizard de setup, shell (sidebar + capçalera + dashboard provisional amb l'estat del sistema) i pàgines «en construcció». Tot amb tokens, els dos temes i navegable per teclat.

## Fora d'abast

- LDAP al login (Fase 2; el backend ja hi cau sol quan existeixi).
- Vinculació amb Gestiona, cerca global (Ctrl+K), badge de pendents.
- Pantalles reals de gestió (usuaris, departaments…): Fase 1, sobre aquest shell.

## Criteris d'acceptació

- [x] Flux complet real: setup wizard → login → shell → logout (provat contra el backend).
- [x] Ruta privada sense sessió → `/login`; amb `needs_setup` → `/setup`.
- [x] La sidebar només mostra entrades permeses per `actions` (test unitari del filtre).
- [x] Error de login mostra títol del Problem i `trace_id`.
- [x] Checklist de força de contrasenya reacciona en viu al wizard.
- [x] `lint`, `typecheck`, tests (unitats + axe de login/setup) i `build` verds.
