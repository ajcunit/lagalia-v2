# LAGALia v2

Plataforma de gestió de la contractació pública de l'**Ajuntament de Cunit**:
sincronització amb fonts obertes, gestió d'expedients i contractes menors,
planificació, auditoria, generació documental amb IA i hub d'integracions.

> **Estat**: repositori inicialitzat amb l'especificació completa i la
> infraestructura de treball. La implementació comença per la Fase 0 del
> [roadmap](docs/09-roadmap.md).

## Com funciona aquest projecte

Es desenvolupa **spec-driven**: les especificacions de `docs/` i el contracte
[`openapi.yaml`](openapi.yaml) són la font de veritat, i canvien **a la mateixa
pull request** que el codi. Res queda desincronitzat.

- Com treballem → [`docs/11-metodologia-specs.md`](docs/11-metodologia-specs.md)
- Què construïm → [`docs/README.md`](docs/README.md) (índex dels 11 documents)
- Què surt pel camí → [`docs/BACKLOG.md`](docs/BACKLOG.md)
- Instruccions per a agents d'IA i gent nova → [`CLAUDE.md`](CLAUDE.md)

## Estructura

```
docs/            Especificacions mestres (01-11), annexos i backlog
specs/           Specs de funcionalitat (una per peça de treball)
openapi.yaml     Contracte de l'API — spec executable, verificada a CI
backend/         API, workers, scheduler (Python 3.12 · FastAPI)   [Fase 0]
frontend/        SPA React 18 + TypeScript + Vite                   [Fase 0]
.github/         Plantilla de PR, CODEOWNERS, workflows de CI
```

## Arrencada de l'entorn de desenvolupament

Requisits: Docker i Docker Compose. (Per treballar fora de contenidor:
Python 3.12 + Node 20.)

```bash
cp .env.example .env       # revisa els valors marcats com a OBLIGATORIS
docker compose up -d       # postgres, redis, minio
```

Un cop existeixi el backend (Fase 0):

```bash
docker compose --profile app up -d --build
```

L'API queda a `http://localhost:8000/api/v1`, la documentació interactiva a
`/docs` i la SPA a `http://localhost:5173`.

## Seguretat

Aquest projecte gestiona dades d'una administració pública i credencials de
sistemes de tercers. Abans de tocar res, llegeix
[`docs/06-seguretat.md`](docs/06-seguretat.md) i la llista de prohibicions
explícites de [`CLAUDE.md`](CLAUDE.md) — no són recomanacions d'estil: recullen
vulnerabilitats reals de l'aplicació anterior que no es poden repetir.

Per reportar un problema de seguretat, contacta directament amb el responsable
del projecte; no obris una incidència pública.

## Llicència

EUPL-1.2 (pendent de confirmació per Secretaria).
