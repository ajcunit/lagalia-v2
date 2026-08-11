# 03 — Arquitectura objectiu

## 1. Visió de conjunt

```
                        ┌─────────────────────────────────────────────┐
                        │                 CLIENTS                      │
                        │  SPA React │ n8n │ Agents IA │ Tercers/SDK   │
                        └──────────────┬──────────────────────────────┘
                                       │ HTTPS (OpenAPI v1)
                        ┌──────────────▼──────────────┐
                        │        API GATEWAY           │  authn (JWT/OIDC), rate limit,
                        │  (reverse proxy + FastAPI)   │  CORS, security headers, tracing
                        └──────┬───────────┬──────────┘
                 ┌─────────────▼──┐   ┌────▼─────────────┐
                 │   CORE API     │   │  AI PLATFORM      │
                 │  (domini)      │   │  (agents/serveis) │
                 │ contractes     │   │ orquestrador      │
                 │ menors         │   │ RAG / indexació   │
                 │ adjudicataris  │   │ generació docs    │
                 │ departaments   │   │ anàlisi/auditoria │
                 │ usuaris, pla   │   │ classificació CPV │
                 │ favorits       │   └────┬──────────────┘
                 └──────┬─────────┘        │
                        │   esdeveniments  │ LLM providers
                 ┌──────▼──────────────────▼──────┐   (Ollama/Gemini/Claude)
                 │        EVENT BUS / JOB QUEUE    │
                 │   (Redis + worker asíncron)     │
                 └──────┬──────────────┬───────────┘
                 ┌──────▼─────┐  ┌─────▼───────────────┐
                 │ WORKERS    │  │  INTEGRATION HUB     │
                 │ sync, enrich│ │  connectors:         │
                 │ alertes,    │ │  socrata, pscp,      │
                 │ indexació   │ │  gestiona, ldap,     │
                 │ webhooks out│ │  smtp, n8n           │
                 └──────┬─────┘  └─────┬───────────────┘
                        │              │
              ┌─────────▼──────────────▼─────────┐
              │  PostgreSQL 16 (+pgvector)       │
              │  + object storage (documents)    │
              └──────────────────────────────────┘
```

**Decisió clau:** monòlit modular ben tallat (no microserveis). Un sol desplegament amb 4 processos: `api`, `worker`, `scheduler` i `frontend` estàtic servit pel proxy. Les fronteres internes (core / ai / integrations) són mòduls Python amb interfícies explícites, cosa que permetria extreure serveis més endavant sense reescriure.

## 2. Components

### 2.1 API Core (FastAPI)
- Routers prims → **casos d'ús** (capa de serveis d'aplicació) → repositoris (SQLAlchemy 2 async). Cap regla de negoci als routers.
- Contracte OpenAPI 3.1 com a font de veritat ([05-api.md](05-api.md)); validació Pydantic v2 a entrada i sortida.
- Publicació d'**esdeveniments de domini** (outbox pattern) a cada escriptura rellevant: `contracte.creat`, `contracte.actualitzat`, `duplicat.detectat`, `sync.completada`, `document.generat`, `alerta.venciment`…

### 2.2 Plataforma d'IA
Mòdul separat amb la seva pròpia API interna i pressupost/quota. Detall a [07-agents-ia.md](07-agents-ia.md). Peces:
- **Provider layer**: abstracció LLM amb **protocol compatible OpenAI com a primera classe** (un adaptador genèric `base_url`+`api_key` cobreix Ollama, vLLM, LM Studio, OpenAI, Azure, OpenRouter...) més adaptadors natius per Gemini i Claude; selecció de perfil+model per tasca, timeouts, retries i comptabilitat de tokens.
- **RAG service**: ingesta de PDFs (plecs històrics, normativa) → extracció (PyMuPDF) → chunking → embeddings a **pgvector** → recuperació híbrida (lèxica + vectorial).
- **Agents**: classificador CPV, auditor de red flags, redactor documental, analista de dades. Cada execució queda registrada (`ai_runs`).

### 2.3 Integration Hub
Detall a [08-hub-integracions.md](08-hub-integracions.md). Connectors com a **plugins activables** amb manifest declaratiu, interfície comuna (`healthcheck`, `credentials`, `capabilities`), credencials xifrades, i execució sempre via jobs — mai dins d'una request HTTP. Dos modes d'execució per plugin: `native` (codi al repositori) i `n8n_bridge` (la lògica viu en un flux n8n darrere del mateix contracte de capacitat), amb migració bridge→natiu sense tocar el domini.

### 2.4 Jobs i esdeveniments
- **Cua**: Redis + worker (arq o Celery; recomanat **arq** per ser async-native i lleuger).
- Jobs idempotents amb clau de deduplicació (p. ex. una sola sync concurrent), reintents amb backoff exponencial, dead-letter queue.
- **Scheduler**: procés únic (no per rèplica) amb locks a BD (advisory locks) per evitar execucions duplicades — resol el defecte v1 d'APScheduler per rèplica.
- **Progrés en temps real**: els jobs escriuen progrés a Redis; l'API l'exposa via `GET /jobs/{id}` (polling) i SSE `GET /jobs/{id}/events` — substitueix els 4 endpoints SSE ad-hoc de la v1 i elimina els tokens per query string (SSE autenticat per cookie de sessió curta o `Last-Event-ID` + token d'un sol ús).

### 2.5 Frontend (SPA React)
Disseny d'interfície complet a [10-ui.md](10-ui.md).
- React 18 + TypeScript + Vite; **TanStack Query** (cache, reintents, invalidació — elimina els `getMe()` duplicats), **client API generat** des de l'OpenAPI (openapi-ts), react-router amb rutes tipades i pàgina 404, context d'usuari únic, Tailwind 4 amb sistema de disseny propi mantenint l'estètica actual (glassmorphism) i mode fosc real.
- Autorització a la UI derivada d'un endpoint `GET /me/permissions` (la UI no dedueix permisos: els rep).
- Recharts per a gràfics; exportacions generades al servidor (CSV/XLSX/DOCX) amb descàrrega per URL signada temporal.

### 2.6 Persistència
- **PostgreSQL 16** amb extensió **pgvector** (RAG) i `pg_trgm` (cerca difusa d'adjudicataris/CPV).
- **Alembic** per a migracions (elimina els `ALTER TABLE` a l'arrencada de la v1).
- **Object storage** per a documents descarregats i generats: sistema de fitxers muntat o MinIO (S3-compatible) segons infraestructura disponible.
- Redis: cua, cache de configuració, rate limiting distribuït, progrés de jobs.

## 3. Stack proposat

| Capa | Tecnologia | Notes |
|---|---|---|
| API | Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 async | continuïtat amb l'equip |
| Cua/jobs | Redis 7 + arq | reintents, cron, locks |
| BD | PostgreSQL 16 + pgvector + pg_trgm | una sola BD |
| LLM | protocol compatible OpenAI (Ollama, vLLM, OpenAI, Azure...) + adaptadors Gemini/Claude | perfils per tasca |
| Frontend | React 18 + TS + Vite + TanStack Query + Tailwind | client generat d'OpenAPI |
| Proxy | Caddy o Nginx | TLS automàtic, headers, compressió |
| Observabilitat | OpenTelemetry + structlog; Prometheus/Grafana opcional | logs JSON |
| Desplegament | Docker Compose (perfil on-premise municipal) | imatges no-root, healthchecks |

## 4. Estructura de codi (backend)

```
backend/
  app/
    core/            # config (pydantic-settings), seguretat, db, telemetria
    domain/          # entitats, value objects, esdeveniments de domini
    modules/
      contracts/     # router, service, repository, schemas
      minor_contracts/
      contractors/   # adjudicataris + àlies + fusions
      departments/
      users/         # empleats, auth, LDAP
      planning/      # pla anual
      favorites/
      audit/         # red flags + auditoria de seguretat (lectura)
      config/
    ai/
      providers/     # ollama, gemini, claude
      rag/           # ingesta, chunking, embeddings, retrieval
      agents/        # cpv, auditor, redactor, analista
    integrations/
      base.py        # interfície Connector
      socrata/       # transparència catalunya (majors, menors, cpv, prorrogues)
      pscp/          # contractaciopublica.cat (enriquiment, documents)
      gestiona/      # pool API + webhook n8n
      ldap/
      smtp/
      webhooks/      # webhooks sortints signats
    jobs/            # definicions de jobs + scheduler
    events/          # outbox, bus, subscriptors
  alembic/
  tests/             # unit, integration (testcontainers), contract (schemathesis)
```

## 5. Decisions i alternatives descartades

| Decisió | Alternativa descartada | Motiu |
|---|---|---|
| Monòlit modular | Microserveis | equip petit, un sol ajuntament; les fronteres modulars ja donen el 90% del benefici |
| PostgreSQL únic (+pgvector) | BD vectorial dedicada (Qdrant...) | menys peces operatives; el corpus és petit (milers de documents) |
| arq + Redis | Celery + RabbitMQ | async natiu, més simple d'operar |
| SSE sobre endpoint genèric de jobs | WebSockets | SSE ja cobreix el cas (progrés unidireccional) i travessa proxies fàcilment |
| JWT propi + refresh rotatiu (com v1) amb opció OIDC | Keycloak obligatori | mantenir simplicitat on-premise; però la capa authn queda aïllada per endollar OIDC (VÀLid / Azure AD) sense tocar el domini |
| Client TS generat d'OpenAPI | client manual (v1) | elimina la deriva contracte-client |

## 6. Requisits no funcionals

- **Rendiment**: llistats < 1 s (50 files); sync 5.000 registres < 5 min; generació de secció documental < 60 s (streaming de tokens a la UI).
- **Disponibilitat**: desplegament single-node acceptable; RTO < 4 h amb backup diari de BD + object storage (script + verificació de restauració).
- **Observabilitat**: tota request amb `trace_id`; tot job amb log estructurat d'inici/fi/errors; mètriques de connectors (latència, errors, quota).
- **i18n**: UI en català; codi i API en anglès (elimina la barreja castellà/català d'identificadors de la v1); dades en la llengua d'origen.
