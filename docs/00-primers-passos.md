# 00 — Primers passos

Guia d'arrencada del repositori nou. Cobreix des de `git init` fins a tenir la
Fase 0 en marxa, amb l'ordre concret de les primeres pull requests.

## 1. Crear el repositori

```bash
# Des de la carpeta lagalia-v2/ ja copiada fora del projecte antic
git init -b main
git add .
git commit -m "chore: bootstrap del projecte amb especificacions i infraestructura"
gh repo create <organitzacio>/lagalia-v2 --private --source=. --push
```

Configuració mínima a la plataforma:
- Protegir `main`: PR obligatòria, CI verda i **una revisió aprovada**.
- Activar CODEOWNERS (revisió obligatòria per a `docs/`, `openapi.yaml` i `specs/`).
- Substituir els comptes d'exemple de `.github/CODEOWNERS` pels reals.
- Crear l'etiqueta `no-spec-change` (excepció documentada per a refactors purs).

## 2. Aixecar l'entorn

```bash
cp .env.example .env
# Genera els dos secrets obligatoris:
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "import base64,os; print('ENCRYPTION_KEY=' + base64.b64encode(os.urandom(32)).decode())"

docker compose up -d          # postgres+pgvector, redis, minio
docker compose ps             # els tres serveis han de sortir healthy
```

## 3. Verificar que la spec executable funciona

```bash
npx @redocly/cli lint openapi.yaml
```

Ha de passar sense errors abans d'escriure la primera línia de codi: és el
contracte del qual es genera el client i contra el qual es valida la implementació.

## 4. Ordre de les primeres pull requests

Cada PR ha de tenir la seva spec (`specs/`) i deixar CI verda. Aquest ordre evita
retreball perquè cada peça és fonament de la següent.

| # | PR | Contingut | Tanca |
|---|---|---|---|
| 1 | `chore: esquelet del backend` | `backend/pyproject.toml` (uv), estructura `app/` de [03-arquitectura.md](03-arquitectura.md) §4, config amb pydantic-settings (falla si falten secrets), logs estructurats, `GET /health` | primera CI de backend verda |
| 2 | `feat: base de dades i migracions` | SQLAlchemy async, Alembic, migració inicial amb `users`, `departments`, `refresh_tokens`, `audit_log` segons [04-model-de-dades.md](04-model-de-dades.md) | esquema base |
| 3 | `feat: autenticació` | login local (Argon2id), refresh amb rotació i famílies, logout, `GET /me`; auditoria de tots els intents | [05-api.md](05-api.md) §2 |
| 4 | `feat: motor d'autorització` | `Authorize(action)`, scopes, abast departamental, `GET /me/permissions`, **test parametritzat rol × acció × abast** d'[annexos/A2](annexos/A2-matriu-permisos.md) | el fonament de tota la resta |
| 5 | `feat: usuaris i departaments` | CRUD complet dels dos recursos de l'`openapi.yaml` inicial, amb baixa lògica i revocació de sessions | tanca l'abast de la Fase 0 al backend |
| 6 | `feat: setup inicial` | `GET /setup/status`, `POST /setup/initialize`, rate limit estricte | primer arrencada usable |
| 7 | `chore: esquelet del frontend` | Vite + TS + Tailwind, tokens de disseny i **els dos temes** ([10-ui.md](10-ui.md) §2), client generat d'OpenAPI, TanStack Query, router amb 404 | CI de frontend verda |
| 8 | `feat: login i shell de l'aplicació` | pantalla d'accés, guard de sessió, sidebar per permisos (una sola crida), assistent de setup | Fase 0 completa |
| 9 | `chore: cua de treballs` | arq + worker + scheduler amb advisory locks, `GET /jobs/{id}` i SSE amb token efímer | prerequisit de la Fase 1 |

A partir d'aquí comença la **Fase 1** ([09-roadmap.md](09-roadmap.md)): connector Socrata i
nucli de contractació, amb [annexos/A1](annexos/A1-mapeig-socrata.md) com a especificació del mapeig.

## 5. Decisions a tancar abans o durant la Fase 1

Del [BACKLOG.md](BACKLOG.md), les que bloquegen:

- **B-001** (P1): mitigar a l'aplicació antiga les dues fuites de secrets, ja que
  continuarà en producció durant tot el projecte.
- **B-002** (P1): validar amb l'entorn de proves de Gestiona l'alternativa a
  enviar el token personal al webhook. Demana coordinació externa: comença-ho aviat.
- **B-003** (P2): confirmar emmagatzematge d'objectes (MinIO o disc muntat).
- **B-005** (P2): llista de normes BOE a subscriure, acordada amb Secretaria.

## 6. Comprovació abans de dir "la Fase 0 està feta"

- [ ] `docker compose --profile app up` aixeca api, worker, scheduler i frontend
- [ ] Un usuari es crea amb el setup wizard i pot iniciar sessió
- [ ] `GET /me/permissions` retorna permisos coherents amb l'annex A2
- [ ] La matriu d'autorització té test automàtic per a cada rol
- [ ] CI: contract testing, lint de seguretat i comprovació spec↔codi, tot verd
- [ ] Un intent de login fallit apareix a `audit_log`
- [ ] La SPA es veu correctament en tema clar i fosc, navegable per teclat

## 7. Desplegament al servidor (test/producció)

El `docker-compose.yml` és **de desenvolupament**: publica la BD, Redis i
MinIO al host per poder-hi entrar des del portàtil. En un servidor això
xoca amb els serveis que ja hi corren (error típic de Portainer:
`Bind for 127.0.0.1:5432 failed: port is already allocated`) i, a més,
exposa la base de dades sense necessitat.

Per al servidor, afegeix sempre l'override de producció:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile app up -d --build
```

Amb l'override, la infraestructura **no publica cap port**: l'API, el
worker i el scheduler hi arriben per la xarxa interna del compose. Només
queden publicats l'API i el frontend, i lligats a `127.0.0.1` perquè hi
arribi el reverse proxy amb TLS (Caddy/Nginx) i ningú més.

**A Portainer**, les variables van a la secció **Environment variables**
de l'stack: pots afegir-les a mà o carregar-hi el `.env` amb «Load
variables from .env file» (Portainer les desa com a variables de
l'stack; l'efecte és el mateix). L'override **no llegeix cap fitxer
`.env` del servidor** justament per això: amb desplegament des de Git el
fitxer no hi és, i els secrets no han d'entrar mai al repositori.

Variables obligatòries (l'stack no arrenca sense elles): `SECRET_KEY`,
`ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `CORS_ORIGINS` i `S3_SECRET_KEY`.
Molt recomanable: `TRUSTED_PROXY_IPS` amb la IP del reverse proxy —
sense això l'auditoria registra la IP del proxy i **tots els usuaris
comparteixen el límit de 5 logins per minut**.

Si algun port publicat encara xoca (per exemple el 8000 ja ocupat),
canvia'l amb variables sense tocar el compose: `API_PORT`,
`FRONTEND_PORT` i, si mai els publiques, `POSTGRES_PORT`, `REDIS_PORT`,
`S3_PORT`, `S3_CONSOLE_PORT`.
