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

Detall complet: [specs/deployment.md](../specs/deployment.md).

El `docker-compose.yml` és **de desenvolupament**: servidor de Vite, sense
proxy i amb la BD publicada al host (això últim xoca amb els serveis que ja
corren al servidor: `Bind for 127.0.0.1:5432 failed: port is already
allocated`). Al servidor es fa servir **`docker-compose.prod.yml`, que és
complet i autònom** — no es combina amb el de desenvolupament:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

A Portainer, «Compose path» = `docker-compose.prod.yml` i prou. (Portainer
CE carrega un sol fitxer: si li passes només una superposició, falla amb
`service "scheduler" has neither an image nor a build context specified`.)

Què canvia: el frontend passa a ser el **build estàtic servit per Caddy**,
que fa de **reverse proxy amb TLS** cap a l'API (mateix origen, com espera
el client). L'única cosa publicada són el 80 i el 443 — ni l'API ni la BD
ni Redis ni MinIO s'exposen al host.

**Variables de l'stack** (a Portainer, *Environment variables*: a mà o amb
«Load variables from .env file»; l'override no llegeix cap `.env` del
servidor, perquè amb desplegament des de Git el fitxer no hi és i els
secrets no han d'entrar al repositori):

- Obligatòries, l'stack no arrenca sense elles i diu quina falta:
  `SECRET_KEY`, `ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `CORS_ORIGINS`,
  `S3_SECRET_KEY`.
- `SITE_ADDRESS`: `https://nom` (TLS automàtic), `nom.local` (certificat
  intern de Caddy) o `:80` (HTTP pla, només amb un altre proxy davant).
- `TRUSTED_PROXY_IPS`: **no** la IP del servidor — el contenidor veu la
  passarel·la de Docker. Accepta rangs; el valor pràctic és
  `172.16.0.0/12`. Sense això, l'auditoria registra la IP del proxy i tots
  els usuaris comparteixen el límit de 5 logins per minut. Per verificar-ho
  després del desplegament, mira la columna `ip` d'`audit_log` en un login:
  hi ha de sortir la IP real de l'usuari.
- Si el 80/443 ja estan ocupats: `HTTP_PORT` i `HTTPS_PORT`.
