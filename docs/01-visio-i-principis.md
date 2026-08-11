# 01 — Visió i principis de disseny

**Projecte:** LAGALia v2 — Plataforma de gestió intel·ligent de la contractació pública
**Organització:** Ajuntament de Cunit
**Data:** Agost 2026
**Estat:** Proposta de re-arquitectura (rebuild des de zero)

---

## 1. Visió

Reconstruir l'actual sistema de gestió de contractació pública com una **plataforma API-first, segura per disseny i nativa d'agents d'IA**, que:

1. **Centralitza** tota la informació de contractació (contractes majors, menors, pla anual, adjudicataris, CPV) sincronitzada des de fonts obertes (Transparència Catalunya / PSCP) i sistemes interns (Gestiona).
2. **Analitza** les dades amb agents d'IA especialitzats (auditoria i red flags, classificació CPV, deteccio de fraccionaments, anàlisi de tendències) de manera traçable i supervisada per humans.
3. **Genera documents** (plecs tècnics PPT, plecs administratius PPA, informes de justificació, informes d'auditoria) mitjançant agents d'IA que treballen sobre documents de referència reals.
4. **S'integra** amb l'ecosistema municipal (Gestiona/esPublico, n8n, LDAP/AD, plataformes de dades obertes) a través d'un **hub d'integracions** desacoblat i extensible.

## 2. Principis rectors

### 2.1 API First

- **El contracte OpenAPI és la font de veritat.** Es dissenya primer l'especificació (OpenAPI 3.1), es genera documentació, SDKs, validació i mocks a partir d'ella. El frontend és *un client més* de l'API.
- **Tota funcionalitat és accessible per API.** No hi ha cap operació que només es pugui fer des de la UI. Això habilita: automatització (n8n), agents d'IA que operen sobre l'API, integracions de tercers i tests E2E reals.
- **Versionat explícit** (`/api/v1/...`) amb política de deprecació documentada.
- **Errors estàndard** (RFC 9457 *Problem Details*), paginació, filtratge i ordenació consistents a tots els recursos.
- **Webhooks i esdeveniments** com a ciutadans de primera classe: qualsevol canvi rellevant emet un esdeveniment consumible.

### 2.2 Seguretat per disseny

- **Zero trust intern:** autenticació i autorització a cada capa, no només al perímetre.
- **RBAC + ABAC centralitzat:** una única política d'autorització (motor de polítiques), no condicions disperses per routers.
- **Secrets fora del codi i fora de la BD en clar:** gestor de secrets o xifrat aplicatiu per a tokens de tercers (Gestiona, Gemini).
- **Auditoria completa i immutable:** qui, què, quan, des d'on — per a totes les escriptures i accessos sensibles.
- **Privacitat per defecte (RGPD/ENS):** minimització de dades personals, retenció definida, registre d'activitats de tractament. Com a administració pública catalana, alineament amb l'**Esquema Nacional de Seguretat (ENS)** nivell mitjà.
- **Cadena de subministrament:** dependències fixades i escanejades, imatges de contenidor signades, SBOM.

### 2.3 Natiu d'agents d'IA

- **Els agents són consumidors de l'API**, amb identitat pròpia, permisos limitats i quota — mai amb credencials d'usuari humà.
- **Human-in-the-loop obligatori** per a qualsevol acció d'escriptura derivada d'IA (validació de suggeriments CPV, aprovació de documents generats, confirmació de red flags).
- **Traçabilitat total de la IA:** cada sortida d'IA registra model, versió del prompt, entrada, cost i qui la va acceptar/rebutjar.
- **Proveïdors intercanviables:** abstracció de proveïdor LLM (local Ollama / API Gemini / API Claude) amb configuració per tasca, no monolítica.
- **RAG sobre corpus propi:** els documents de contractació (plecs històrics, normativa) indexats per a recuperació semàntica, base de la generació documental.

### 2.4 Hub d'integracions

- **Connectors com a mòduls independents** amb cicle de vida propi (habilitar/deshabilitar, credencials, salut, logs) — Gestiona, Transparència Catalunya, PSCP/contractaciopublica.cat, LDAP/AD, n8n, SMTP.
- **Sincronitzacions com a jobs gestionats:** cua de treballs amb reintents, backoff, idempotència i observabilitat (no crides síncrones dins de requests HTTP).
- **Esdeveniments sortints (webhooks)** signats i amb reintents, perquè sistemes externs reaccionin a canvis (nou contracte, duplicat detectat, document generat).

### 2.5 Especificacions sincronitzades (spec-driven)

- **Les especificacions són la font de veritat**, no documentació escrita a posteriori: el codi, les specs i l'OpenAPI viuen al mateix repositori i canvien a la mateixa pull request.
- **Res no queda desincronitzat**: si el codi es desvia d'una spec, s'actualitza la spec (o es marca la desviació i s'obre entrada de backlog) — mai una divergència silenciosa. El contract testing ho fa complir automàticament per a l'API.
- **Tot el que sorgeix durant el desenvolupament passa pel backlog** amb prioritat i esbós de com desenvolupar-ho, abans d'implementar-se.
- Detall operatiu a [11-metodologia-specs.md](11-metodologia-specs.md).

### 2.6 Qualitat operativa

- **Observabilitat:** logs estructurats, mètriques, traces (OpenTelemetry).
- **Tests com a requisit:** contract testing contra l'OpenAPI, tests d'integració de connectors, tests E2E dels fluxos crítics.
- **Migracions de BD gestionades** (Alembic) — mai scripts manuals.
- **Desplegament reproduïble:** Docker Compose per a on-premise municipal, amb camí clar cap a Kubernetes si cal.

## 3. Objectius mesurables

| Objectiu | Mètrica |
|---|---|
| Paritat funcional amb la v1 | 100% dels casos d'ús inventariats a `02-especificacio-funcional.md` |
| API completa | Tota operació de la UI disponible i documentada a OpenAPI |
| Seguretat | 0 secrets en clar; auditoria del 100% d'escriptures; autorització centralitzada |
| IA traçable | 100% de sortides d'IA amb registre de model/prompt/acceptació |
| Sincronització | < 5 min per 5.000 registres; 0 pèrdua de dades; reintents automàtics |
| Integracions | Alta d'un connector nou sense tocar el nucli |

## 4. Fora d'abast (v2 inicial)

- App mòbil nativa.
- Tramitació electrònica completa (signatura, notificació) — es delega a Gestiona.
- Multi-tenant per a altres ajuntaments (es deixa el disseny preparat: `codi_ine10` com a discriminador, però una sola organització per desplegament).

## 5. Documents del paquet

| Doc | Contingut |
|---|---|
| [02-especificacio-funcional.md](02-especificacio-funcional.md) | Inventari complet de funcionalitats de la v1 (paritat) |
| [03-arquitectura.md](03-arquitectura.md) | Arquitectura objectiu, components, stack |
| [04-model-de-dades.md](04-model-de-dades.md) | Model de dades v2 |
| [05-api.md](05-api.md) | Disseny API-first: convencions i mapa de recursos |
| [06-seguretat.md](06-seguretat.md) | Seguretat per disseny: authn/authz, secrets, auditoria, ENS |
| [07-agents-ia.md](07-agents-ia.md) | Plataforma d'agents d'IA: anàlisi de dades i generació documental |
| [08-hub-integracions.md](08-hub-integracions.md) | Hub d'integracions: connectors, jobs, webhooks |
| [09-roadmap.md](09-roadmap.md) | Fases de construcció i migració des de la v1 |
| [10-ui.md](10-ui.md) | Interfície d'usuari: sistema de disseny, patrons, accessibilitat |
| [11-metodologia-specs.md](11-metodologia-specs.md) | Metodologia spec-driven: sincronització spec↔codi, backlog, definició de fet |
| [BACKLOG.md](BACKLOG.md) | Backlog viu del projecte |
