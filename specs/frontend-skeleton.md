# Esquelet del frontend (Estat: implementada)

## Context i objectiu

Setena PR de la Fase 0 ([00-primers-passos.md](../docs/00-primers-passos.md) §4): la base tècnica de la SPA segons [10-ui.md](../docs/10-ui.md) — sistema de tokens amb els dos temes des del primer component, client HTTP generat del contracte i infraestructura d'i18n. La pantalla de login i el shell arriben amb la PR #8.

## Comportament

Donat el repositori amb `openapi.yaml` vàlid,
Quan s'executa `npm run dev` (o el contenidor del compose),
Aleshores la SPA arrenca, mostra la pàgina d'inici amb l'estat real de l'API (`/health` i `/setup/status` via client generat) i respon amb la pàgina 404 pròpia a rutes desconegudes.

Regles verificables:

- **Stack** ([03-arquitectura.md](../docs/03-arquitectura.md) §2.5): Vite + React 18 + TypeScript estricte + Tailwind 4 + TanStack Query + React Router.
- **Client generat, mai a mà**: `npm run generate:api` executa `openapi-typescript` sobre `../openapi.yaml` cap a `src/api/generated/`; `openapi-fetch` el consumeix amb tipus. La CI falla si el generat no coincideix amb el contracte.
- **Tokens de disseny** (`src/styles/tokens.css`): colors semàntics (`--surface`, `--ink`, `--muted`, `--accent`, `--success/warning/danger/info`), radis, ombres. **Cap color literal als components**; Tailwind els mapeja com a utilitats via `@theme`.
- **Dos temes reals**: clar i fosc definits a nivell de token; detecció de `prefers-color-scheme` + preferència persistida (`localStorage`), aplicada abans del primer paint (sense flaix). Contrast AA validat als tokens.
- **Tipografia**: Inter autoallotjada (@fontsource, empaquetada al build; cap CDN), `tabular-nums` disponible com a utilitat.
- **i18n des del principi**: claus de traducció tipades (`t("...")`) amb catàleg `ca`; cap string d'UI incrustat als components.
- **Router amb 404 pròpia** i estructura per a rutes de creació explícites.
- **L'estat de l'API a la pàgina d'inici** es carrega amb TanStack Query (una consulta per recurs, `staleTime` generós).
- **Accessibilitat**: skip link, focus visible, `lang="ca"`, test automàtic amb axe a CI (`npm run test:a11y`).
- **Qualitat a CI**: `lint` (ESLint), `typecheck` (tsc estricte), `test` (Vitest + Testing Library), `build`, comprovació del client generat, axe.

## Canvis d'API

Cap: el frontend consumeix el contracte existent.

## Canvis de dades

Cap.

## Seguretat i permisos

- El dev server fa proxy de `/api` cap al backend; mai URLs d'API incrustades amb credencials.
- Cap lògica de negoci ni deducció de permisos al frontend (arribarà de `/me/permissions`, PR #8).

## UI

Pàgina d'inici provisional (nom de l'aplicació, estat de l'API, estat del setup, toggle de tema) i pàgina 404. El shell definitiu, a la PR #8.

## Fora d'abast

- Login, guard de sessió, sidebar per permisos i setup wizard (PR #8).
- Biblioteca de components completa (Button, DataTable…) — creix amb les pantalles.
- Storybook/Ladle, Playwright E2E (amb les primeres pantalles reals).

## Criteris d'acceptació

- [x] `npm run dev` mostra la pàgina d'inici amb l'estat real de l'API.
- [x] Ruta desconeguda → pàgina 404 pròpia.
- [x] Toggle de tema clar/fosc persistit i sense flaix inicial; ambdós temes definits als tokens.
- [x] `npm run generate:api` és idempotent sobre el contracte actual (CI ho vigila).
- [x] `lint`, `typecheck`, `test` (incloent axe) i `build` verds.
- [x] Contenidor Docker del compose (`--profile app`) construïble.
