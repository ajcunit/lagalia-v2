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

### TLS (`SITE_ADDRESS`)

| Valor | Efecte |
|---|---|
| `https://lagalia.cunit.cat` | HTTPS automàtic (Let's Encrypt) si el nom resol des d'Internet i 80/443 són oberts |
| `lagalia.local` | Certificat intern de Caddy (LAN); cal confiar en la seva CA als navegadors |
| `:80` | HTTP pla; **només** si ja hi ha un altre proxy amb TLS davant |

### Capçaleres de seguretat

El proxy afegeix HSTS, `X-Content-Type-Options`, `X-Frame-Options: DENY`,
`Referrer-Policy`, `Permissions-Policy` i **CSP** (`default-src 'self'`;
`style-src` amb `'unsafe-inline'` pels estils en línia dels components; cap
CDN) i amaga la capçalera `Server`. Tanca la debilitat 16 de
docs/06-seguretat.md §2 (la v1 no tenia CSP ni HSTS).

### Configuració

Sense fitxer `.env` al servidor: les variables són de l'stack (a Portainer,
*Environment variables*, a mà o carregant-hi un `.env`). Obligatòries —
l'stack falla ràpid amb el nom de la que falta: `SECRET_KEY`,
`ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `CORS_ORIGINS`, `S3_SECRET_KEY`.

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
