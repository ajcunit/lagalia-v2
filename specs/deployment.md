# Desplegament al servidor (Estat: implementada)

## Context i objectiu

docs/03-arquitectura.md §2 prometia un «Docker Compose complet (proxy TLS,
api, worker, scheduler, postgres+pgvector, redis, minio)» que no existia:
el compose era només de desenvolupament (servidor de Vite, sense proxy, amb
la BD publicada al host). Detectat en desplegar per primera vegada a
Portainer (2026-08-19).

## Comportament

Desplegament = els dos fitxers de compose:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile app up -d --build
```

### Topologia

- **Una sola entrada publicada**: el servei `frontend` en producció és
  **Caddy** (`frontend/Dockerfile.prod`: build de Vite → imatge
  `caddy:2-alpine`), que serveix la SPA estàtica i fa de **reverse proxy**
  de `/api/*` cap a `api:8000`. Mateix origen per a SPA i API, com espera
  el client TS (`baseUrl: "/api/v1"`).
- **L'API no es publica** al host: hi arriba el proxy per la xarxa interna.
- **La infraestructura tampoc**: BD, Redis i MinIO només per xarxa interna
  (evita xocs de ports al servidor i no exposa la base de dades).
- Volums `caddydata`/`caddyconfig`: els certificats sobreviuen als
  desplegaments (si no, es tornarien a emetre a cada reinici).
- Sense `profiles`: tot l'stack puja de cop (Portainer no passa `--profile`).

### TLS (`SITE_ADDRESS`)

| Valor | Efecte |
|---|---|
| `https://lagalia.cunit.cat` | HTTPS automàtic (Let's Encrypt) si el nom resol des d'Internet i 80/443 són oberts |
| `lagalia.local` | Certificat intern de Caddy (LAN); cal confiar en la seva CA als navegadors |
| `:80` | HTTP pla; **només** si ja hi ha un altre proxy amb TLS davant |

### Darrere d'un proxy que ja existeix (cas de Cunit)

L'Ajuntament ja té un **Traefik en un altre servidor** que serveix
`https://lagalia-contractacio.ajcunit.local` cap al port 5173 d'aquest host.
El TLS **no** el fa Caddy:

```
SITE_ADDRESS=:80      # HTTP pla; el TLS és del Traefik
HTTP_PORT=5173        # el port que ataca el Traefik: cap canvi a la seva config
HTTPS_PORT=8443       # el 443 és del Traefik; aquí, un port lliure qualsevol
```

**Cadena de proxys**: el Caddyfile declara `trusted_proxies static
private_ranges` i reenvia a l'API un únic `X-Forwarded-For` amb
`{remote_host}`. Així Caddy resol la IP real del client a partir de la
capçalera del Traefik, i l'API (amb `TRUSTED_PROXY_IPS=172.16.0.0/12`) veu
el client real: auditoria i límit de login correctes al llarg de tota la
cadena. Verificat en local amb una capçalera simulada
(`client_ip` als registres de Caddy = la IP injectada).

Com que el Traefik és **a un altre servidor**, el port s'ha de publicar a
totes les interfícies (no val `127.0.0.1`, ni connectar el contenidor a la
seva xarxa Docker).

> ⚠️ Conseqüència: qualsevol màquina de la LAN pot atacar el port
> directament, saltant-se el Traefik, i falsificar `X-Forwarded-For` (IP de
> l'auditoria i bucket del límit de login). El tràfic entre servidors va en
> HTTP pla. Enduriment pendent (BACKLOG B-020): regla de tallafocs a la
> cadena `DOCKER-USER` que només permeti el 5173 des de la IP del Traefik.

### Capçaleres de seguretat

El proxy afegeix HSTS, `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Referrer-Policy`, `Permissions-Policy` i **CSP** (`default-src 'self'`;
`style-src` amb `'unsafe-inline'` pels estils en línia dels components; cap
CDN) i amaga la capçalera `Server`. Tanca la debilitat 16 de
docs/06-seguretat.md §2 (la v1 no tenia CSP ni HSTS).

### Migracions

Un servei **`migrate`** d'un sol ús executa `alembic upgrade head` i acaba;
`api`, `worker` i `scheduler` esperen que hagi acabat bé
(`service_completed_successfully`). Així l'esquema existeix abans que
arrenqui res i mai hi ha dos processos migrant alhora.

### Dependències de la imatge: guardià al build

La imatge fa `uv sync --frozen --no-dev` i prou, mentre que `uv run` (CI i
local) re-sincronitza el lock i instal·la també el grup `dev`. Això va
amagar **dos** defectes que només apareixien al servidor:

1. `uv.lock` endarrerit → faltaven pgvector, ldap3, pymupdf, python-docx,
   python-multipart i tzdata (el `migrate` moria amb
   `ModuleNotFoundError: pgvector`).
2. `httpx` declarat al grup **dev** tot i que el codi de producció
   l'importa a cinc mòduls (l'API no arrencava).

Per tancar la categoria sencera, el `Dockerfile` **importa tots els mòduls
de `app/`** després d'instal·lar (165 mòduls) amb dependències de producció
només: si en falta cap, el build falla allà i no al desplegament. El CI, a
més, comprova `uv lock --check`.

> ⚠️ Perquè les migracions corrin dins de la imatge, el **`uv.lock` ha
> d'estar al dia**: la imatge fa `uv sync --frozen` i res més, mentre que
> `uv run` (CI i local) re-sincronitza el lock en silenci. Sis dependències
> (pgvector, ldap3, pymupdf, python-docx, python-multipart, tzdata) hi
> faltaven i el `migrate` petava amb `ModuleNotFoundError: pgvector`. El CI
> ho comprova ara amb `uv lock --check`.

La imatge del backend inclou `alembic.ini` i `alembic/` (abans només hi
havia `app/`: sense això, cap desplegament creava les taules — es veia com
«arribo al login però no em demana el wizard», perquè `GET /setup/status`
petava i el frontend es quedava al formulari). El formulari de login ara
avisa explícitament si aquesta comprovació falla.

### Configuració

Sense fitxer `.env` al servidor: les variables són de l'stack (a Portainer,
*Environment variables*, a mà o carregant-hi un `.env`). Obligatòries —
l'stack falla ràpid amb el nom de la que falta: `SECRET_KEY`,
`ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `S3_SECRET_KEY`.

`CORS_ORIGINS` queda **buit** en el desplegament estàndard: la SPA i l'API
comparteixen origen (les peticions del mateix origen no passen per CORS).
Només s'omple si un altre domini ataca l'API. El middleware de CORS
s'instal·la només si hi ha orígens declarats i **rebutja `"*"`** (s'envien
credencials, 06 §5) — abans el paràmetre existia però el middleware no
estava connectat: no feia res.

`TRUSTED_PROXY_IPS` accepta IPs i **rangs CIDR**: amb Docker no hi va la IP
del servidor (el contenidor veu la passarel·la de la xarxa del compose, o
la IP del contenidor del proxy, que canvia). Valor pràctic:
`172.16.0.0/12`. Sense això l'auditoria registra la IP del proxy i tots els
usuaris comparteixen el límit de login.

`OUTBOUND_CA_BUNDLE` apunta a `./ops/outbound-ca-bundle.pem`, que l'override
munta dins del contenidor (a la imatge només hi ha `app/`).

## Canvis d'API

Cap.

## Fora d'abast

- Backups automàtics de BD i object storage + verificació de restauració
  (docs/03 §3: RTO < 4 h) — pendent.
- Rèpliques/alta disponibilitat: single-node acceptat a docs/03.

## Criteris d'acceptació

- [x] La imatge de producció construeix i serveix la SPA, amb fallback de
  rutes de client i capçaleres de seguretat (provat en local).
- [x] Cap port d'infraestructura publicat; només 80/443.
- [x] `docker compose config` vàlid amb les variables de l'stack.
