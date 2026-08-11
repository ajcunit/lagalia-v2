# Backend skeleton (Estat: implementada)

## Context i objectiu

La primera PR del projecte crea l'esquelet del backend de LAGALia v2 i deixa una base sanejada per a les següents fases del roadmap. L'objectiu és que l'API pugui arrencar en local, exposi un endpoint de salut públic i estigui preparada per a configuració centralitzada, logs estructurats i modularització per mòduls.

## Comportament

Donat que el repositori té la infraestructura base i la definició d'API de [openapi.yaml](../openapi.yaml),
Quan s'executa el backend en local,
Aleshores ha de respondre en el path `/api/v1/health` amb un JSON `{ "status": "ok", "version": "0.1.0" }` i ha de poder servir la documentació d'OpenAPI a `/docs`.

Regles verificables:

- La app s'ha de poder iniciar amb `uv run uvicorn app.main:app` o mitjançant Docker.
- L'endpoint `/health` ha de ser públic i no exigir autenticació.
- La configuració es llegeix des de variables d'entorn amb valors per defecte segurs per a
  desenvolupament (`debug=false`, logs JSON), via pydantic-settings a `app/core/config.py`.
- **L'aplicació no arrenca si falten els secrets obligatoris** (`SECRET_KEY`,
  `ENCRYPTION_KEY`), i valida que tinguin la forma correcta (mínim 32 caràcters;
  base64 de 32 bytes respectivament). Els secrets es tipen com a `SecretStr` i no
  apareixen mai a `repr()` ni als logs.
- Els logs són estructurats (structlog): JSON en producció, consola en desenvolupament.
- Les imports i l'estructura de projecte segueixen l'arquitectura de
  [docs/03-arquitectura.md](../docs/03-arquitectura.md) §4.
- Les dependències es gestionen amb **uv** i lockfile versionat (`uv.lock`); la CI
  instal·la amb `uv sync --frozen`.

## Canvis d'API

Cap canvi de l'OpenAPI ja definit en [openapi.yaml](../openapi.yaml): es compleix l'endpoint `/health` actual. `/health/ready` queda fora d'abast (necessita base de dades, PR #2).

## Canvis de dades

Cap. Aquesta PR no modifica el model de dades ni l'esquema de PostgreSQL.

## Seguretat i permisos

L'endpoint `/api/v1/health` és públic. No hi ha secrets ni dades sensibles a les respostes, i no es registra informació personal. El contenidor Docker s'executa amb un usuari sense privilegis.

## UI

Cap.

## Fora d'abast

- Autenticació i autorització.
- Migracions de base de dades i `/health/ready`.
- Jobs i integracions.

## Criteris d'acceptació

- [x] `uv sync` instal·la el projecte i les dependències de desenvolupament.
- [x] `GET /api/v1/health` retorna `200` i el payload esperat.
- [x] La documentació OpenAPI és accessible a `/docs`.
- [x] La configuració del servei es centralitza a `app/core/config.py` i falla amb secrets absents o mal formats (amb test).
- [x] Logs estructurats configurats a `app/core/logging.py`.
- [x] El projecte inclou un `Dockerfile` per arrencar-se amb Compose (usuari no root).
- [x] `ruff check`, `ruff format --check` i `mypy --strict` passen nets.
