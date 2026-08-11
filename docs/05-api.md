# 05 — Disseny API-first

## 1. Principis

1. **OpenAPI 3.1 com a contracte**: el fitxer `openapi.yaml` es versiona al repositori i és la referència; el codi FastAPI el materialitza i un test de CI comprova que no hi ha deriva (schemathesis / oasdiff). El client TS del frontend i els SDKs es generen del contracte.
2. **Tota funcionalitat per API**: la UI no fa res que un agent d'IA o n8n no pugui fer amb un token adequat.
3. **Versionat**: prefix `/api/v1`; canvis incompatibles → `/api/v2` amb període de convivència; capçalera `Deprecation` + `Sunset` per anunciar retirades.
4. **Errors**: RFC 9457 `application/problem+json` — `{type, title, status, detail, instance, trace_id, errors[]}`. Mai cossos de request reflectits a la resposta (fuita v1 corregida).
5. **Paginació**: `?page[size]=&page[cursor]=` (cursor-based per a llistats grans) amb `meta: {total, next_cursor}`. Filtres i ordenació homogenis: `?filter[camp]=valor&sort=-published_at`.
6. **Idempotència**: capçalera `Idempotency-Key` a POST crítics (creació de contracte, llançament de jobs, webhooks).
7. **Camps parcials**: `?fields=` per a respostes primes (agents d'IA que només volen 3 camps).

## 2. Autenticació i autorització

| Consumidor | Mecanisme |
|---|---|
| SPA (usuaris humans) | `POST /auth/login` → JWT accés (15-30 min) + refresh rotatiu amb família (detecció de reutilització). Opció OIDC endollable |
| Agents d'IA / n8n / integracions | **API keys de servei** (`Authorization: Bearer sk_...`) amb *scopes* granulars i caducitat; gestió a `/service-accounts` |
| SSE / descàrregues | token efímer d'un sol ús emès per l'API (`POST /auth/ephemeral`) — mai el JWT a la query string |

**Scopes** (exemples): `contracts:read`, `contracts:write`, `sync:execute`, `ai:run`, `config:read`, `config:write`, `webhooks:manage`, `audit:read`. Els rols humans es mapegen a conjunts de scopes; el motor d'autorització (vegeu 06 §3) avalua scope + abast departamental.

## 3. Mapa de recursos (v1 de l'API nova)

### Contractes
```
GET    /contracts                     llistat (filtres §1.5 de 02; dedupe per expedient amb ?group_by=file)
POST   /contracts                     alta manual
GET    /contracts/{id}                detall (inclou lots germans, comptadors)
PATCH  /contracts/{id}                edició parcial (matriu de permisos)
GET    /contracts/{id}/history        historial
GET    /contracts/{id}/extensions     pròrrogues
GET    /contracts/{id}/modifications  modificacions
GET    /contracts/{id}/documents      documents per fase
POST   /contracts/{id}/actions/finish            estat → Finalitzat
POST   /contracts/{id}/actions/dismiss-expiry    descarta alerta
POST   /contracts/{id}/actions/enrich            job d'enriquiment individual
POST   /contracts/{id}/actions/open-in-gestiona  webhook Gestiona
POST   /contracts/bulk/assign-departments        assignació massiva
GET    /contracts/exports?format=csv|xlsx        job d'export → URL signada
GET    /contracts/stats               dashboard (filtres year, amount_min/max)
GET    /contracts/facets              valors distinct per a filtres
```

### Menors, adjudicataris, organització
```
GET/PATCH        /minor-contracts, /minor-contracts/{id}
POST             /minor-contracts/bulk/assign-departments
GET              /contractors                     rànquing unificat
GET              /contractors/{id}                detall + històric (per id, no nom-en-base64)
GET/POST         /contractors/duplicates          deteccions
POST             /contractors/duplicates/{id}/actions/resolve   (merge_1|merge_2|reject)
GET/POST/PATCH/DELETE  /departments, /departments/{id} (+ /users, /contracts niats)
GET              /departments/gestiona-groups     proxy connectors
GET/POST/PATCH/DELETE  /users, /users/{id}
GET/PATCH        /me            perfil propi
GET              /me/permissions                  permisos efectius per a la UI
POST             /me/integrations/gestiona/{authorize|check|link}
```

### Sincronització, duplicats, jobs
```
POST   /sync-runs                {kind: contracts|minor|cpv|enrichment|extensions}  → 202 + job
GET    /sync-runs, /sync-runs/{id}
GET    /duplicates?status=pending
POST   /duplicates/{id}/actions/resolve     {action, notes}
GET/POST/PATCH/DELETE  /association-rules
GET    /jobs/{id}                estat + progrés
GET    /jobs/{id}/events         SSE de progrés (token efímer)
POST   /jobs/{id}/actions/cancel
```

### Referència i cerca
```
GET    /cpv?query=&level=&parent=            cerca + arbre
GET    /public-registry/search               superbuscador (proxy Socrata parametritzat, mai SoQL cru)
GET    /public-registry/contracts/{file_code}
GET    /public-registry/phase?url=           proxy validat per whitelist (autenticat)
GET/POST/PATCH/DELETE  /folders, /folders/{id}/favorites
POST   /folders/{id}/favorites/by-file-code  importa extern si cal
```

### Tasques i recordatoris
```
GET    /tasks                        les meves / del departament (filtres: status, due_before/after, contract_id, assignee)
POST   /tasks                        crear (amb reminders[] i recurrence opcional)
GET/PATCH/DELETE  /tasks/{id}
POST   /tasks/{id}/actions/complete | /cancel | /reopen
GET    /contracts/{id}/tasks         pestanya de la fitxa (també /minor-contracts/{id}/tasks)
GET    /tasks/calendar?from=&to=&department_id=   vista calendari
GET    /tasks/suggestions            tasques proposades per alertes (pròrroga, venciment) → acceptar/descartar
GET    /me/tasks.ics?key=            feed iCal per subscripció (clau signada per usuari, revocable)
```

### Pla i generador documental
```
GET/POST/PATCH/DELETE  /plan-entries?fiscal_year=
GET    /plan-entries/expiring-contracts?fiscal_year=
GET/POST/DELETE  /doc-projects
GET/PUT          /doc-projects/{id}/documents/{type}
POST   /doc-projects/{id}/documents/{type}/actions/generate-index      → ai_run/job
POST   /doc-projects/{id}/documents/{type}/sections/{n}/actions/draft  → ai_run/job (streaming)
POST   /doc-projects/{id}/documents/{type}/exports   {format: docx|pdf} → URL signada
```

### Plataforma d'IA
```
POST   /ai/cpv-suggestions          {subject} → 5 candidats amb score i justificació
POST   /ai/audit-analyses           {custom_prompt?} → informe (job + streaming)
POST   /ai/analyses                 anàlisi de dades ad-hoc (agent analista, vegeu 07)
GET    /ai/runs, /ai/runs/{id}      traçabilitat
POST   /ai/runs/{id}/actions/accept|reject
GET/PUT /ai/prompts/{task}          versions de prompt (admin)
POST   /contracts/{id}/actions/legal-review        revisió legal (regles + LLM) → informe
POST   /doc-projects/{id}/documents/{type}/actions/legal-review
GET    /compliance-reviews, /compliance-reviews/{id}
GET/PATCH /compliance-rules          regles deterministes (admin; versionades per data d'efecte)
GET/POST/DELETE /legal/norms         normes BOE subscrites (+estat de consolidació)
GET/POST/PATCH/DELETE  /ai/provider-profiles     perfils LLM (protocol openai_compatible|gemini|claude)
POST   /ai/provider-profiles/{id}/actions/test   prova de connexió + autodetecció de models
GET    /ai/provider-profiles/{id}/models         llista via /v1/models del proveïdor
```

### Auditoria i administració
```
GET    /audit/red-flags/{splitting|abnormal-bids|low-competition|expiring}
GET    /audit/security-log          (admin, filtres actor/acció/data)
GET/PUT /settings/{key}             (secrets: write-only, retorna is_set)
GET    /connectors                  plugins registrats (manifest, mode, salut)
PATCH  /connectors/{slug}           activar/desactivar, config, canvi de mode native|n8n_bridge
POST   /connectors/{slug}/actions/test
GET/POST/DELETE /webhooks           webhooks sortints
GET    /webhooks/{id}/deliveries
GET/POST/DELETE /service-accounts   API keys per a agents/integracions
GET    /setup/status 🔓, POST /setup/initialize 🔓
GET    /health 🔓 (liveness), GET /health/ready (readiness amb estat de dependències, autenticat)
```

## 4. Esdeveniments (contracte asíncron)

Tots els esdeveniments segueixen CloudEvents JSON: `{id, source, type, time, subject, data}`.

| Tipus | Quan |
|---|---|
| `contract.created` / `contract.updated` / `contract.finished` | escriptures al nucli |
| `contract.duplicate_detected` | sync detecta parell |
| `contract.expiry_warning` | transició d'alerta de venciment |
| `task.due_soon` / `task.overdue` / `task.completed` | recordatoris i cicle de vida de tasques |
| `sync.completed` / `sync.failed` | fi de job de sincronització |
| `document.generated` | export documental llest |
| `ai.run_completed` | execució d'agent acabada |
| `contractor.merged` | fusió d'adjudicataris |
| `legal.norm_updated` | el BOE consolida un canvi en una norma subscrita |
| `compliance.review_completed` | informe de revisió legal disponible |

Consumibles per: webhooks sortints signats (HMAC SHA-256 a `X-Signature`, timestamp anti-replay, reintents exponencials), i internament pels subscriptors (emails, indexació RAG, notificacions).

## 5. Regles de qualitat del contracte

- Tot endpoint amb: `operationId` estable, descripció, exemples de request/response, esquemes d'error, scopes requerits (`x-required-scopes`).
- Enums tancats documentats (estats, accions) — cap "string lliure" on el domini és finit.
- Dates ISO 8601 UTC amb sufix `Z`; imports com a string decimal (evita floats).
- Límits explícits: `page[size] ≤ 500`, timeouts documentats, rate limits anunciats amb capçaleres `RateLimit-*`.
- Compatibilitat: afegir camps és segur; eliminar-ne o canviar tipus exigeix versió nova.
