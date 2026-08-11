# Setup inicial (Estat: implementada)

## Context i objectiu

Sisena PR de la Fase 0 ([00-primers-passos.md](../docs/00-primers-passos.md) §4): primera arrencada usable. Implementa la detecció de sistema no inicialitzat i la creació de l'administrador inicial amb la configuració per defecte ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.1).

## Comportament

Donat un sistema sense cap usuari,
Quan es crida `POST /setup/initialize` amb nom, correu i contrasenya vàlids,
Aleshores es crea l'usuari `admin`, es desa la configuració per defecte i el sistema deixa d'acceptar inicialitzacions.

Regles verificables:

- **`GET /setup/status`** (públic): `{needs_setup: true}` només quan hi ha **0 usuaris**. És l'únic endpoint que revela informació abans d'autenticar-se, i només aquest booleà.
- **`POST /setup/initialize`** (públic, rate limit estricte):
  - Amb usuaris existents → `403` Problem (`already-initialized`), auditat.
  - Concurrent-safe: advisory lock transaccional + re-comprovació dins de la transacció; dues crides simultànies no poden crear dos admins.
  - Crea l'usuari amb rol `admin`, contrasenya sotmesa a la política del contracte (12+, majúscula, minúscula, xifra, no filtrada).
  - Desa la configuració inicial a `settings`: `org.name` i `org.ine10_code` (si arriben; `ine10_code` valida `^[0-9]{10}$`) i `setup.completed_at`. Els valors per defecte de sincronització, IA i prompts arriben amb els seus mòduls (Fase 1+), que faran servir aquesta mateixa taula.
  - Resposta `201` amb l'esquema `User`; auditat com a `setup.initialize` amb l'admin creat com a actor.
  - **Rate limit estricte**: 3 intents/hora per IP → `429` amb `Retry-After`.
- **Migració 0002**: taula `settings` segons [04-model-de-dades.md](../docs/04-model-de-dades.md) §5 (`key UNIQUE`, `value JSONB`, `description`, `is_secret`, `updated_by`, timestamps amb trigger). S'avança a la Fase 0 perquè el setup hi desa la configuració; el comportament `is_secret=true` (xifrat + `is_set`) arriba amb el mòdul de configuració.

## Canvis d'API

Cap canvi de contracte: implementa `GET /setup/status` i `POST /setup/initialize` tal com són a [openapi.yaml](../openapi.yaml).

## Canvis de dades

Migració `0002_settings`: taula `settings` + trigger `updated_at`. Reversible.

## Seguretat i permisos

- El setup no retorna cap `TokenPair`: l'admin creat inicia sessió pel login normal (auditat).
- La contrasenya mai apareix a logs, auditoria ni respostes; el correu de l'admin només a l'auditoria.
- `settings.updated_by` és NULL al setup (encara no hi ha actor autenticat en el moment d'escriure).

## UI

Cap (l'assistent de 4 passos arriba amb la PR #8).

## Fora d'abast

- Mòdul de configuració (`GET/PUT /config`, secrets xifrats amb `is_set`): Fase 1.
- Valors per defecte de sincronització, IA i prompts (els seus mòduls els sembren de manera idempotent).
- Wizard de frontend.

## Criteris d'acceptació

- [x] `GET /setup/status` reflecteix exactament `count(users) == 0`.
- [x] `POST /setup/initialize` amb el sistema ja inicialitzat → `403` auditat.
- [x] Sobre una BD buida: `201`, usuari admin funcional (login OK), settings sembrats, `needs_setup` passa a `false`.
- [x] 4t intent en una hora des de la mateixa IP → `429` amb `Retry-After`.
- [x] Contrasenya feble → `422` sense eco del valor.
- [x] `alembic upgrade head`/`downgrade` de la 0002 provats.
- [x] `ruff`, `mypy --strict` i tota la suite verds.
