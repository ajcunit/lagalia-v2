# 09 — Roadmap de construcció i migració

Estratègia: **reescriptura completa en repositori nou** amb la v1 en producció intacta fins al tall. La migració de dades és un script reproduïble que es pot executar tantes vegades com calgui (assajos setmanals contra còpia de producció).

## Fase 0 — Fonaments (2-3 setmanes)

- Repositori nou, CI/CD (lint + seguretat + tests + build d'imatges), entorns (dev/staging).
- **Infraestructura spec-driven** ([11-metodologia-specs.md](11-metodologia-specs.md)): carpeta `specs/`, plantilla de PR amb checklist de sincronització, CODEOWNERS sobre `docs/rebuild/**` i `openapi.yaml`, contract testing a CI i check de "codi sense spec". Cal que existeixi abans d'escriure la primera feature.
- Esquelet backend (estructura de [03-arquitectura.md](03-arquitectura.md) §4): config, BD async, Alembic, Redis+arq, telemetria, `authz`, middleware de seguretat.
- Contracte OpenAPI inicial (auth, users, departments, health) + generació del client TS.
- Esquelet frontend: layout, login, guards, TanStack Query, sistema de disseny (portant l'estètica v1).
- Docker Compose complet (proxy TLS, api, worker, scheduler, postgres+pgvector, redis, minio).

**Sortida:** desplegament buit funcional amb login, setup wizard i auditoria de seguretat activa.

## Fase 1 — Nucli de contractació (4-5 setmanes)

- Model de dades complet + migracions.
- Connector `socrata` + jobs de sync (contractes, menors, pròrrogues, CPV) amb progrés observable.
- Connector `pscp` (enriquiment + documents a object storage).
- Contractes: llistats, detall, edició amb matriu de permisos, historial, creació manual, exports server-side.
- Menors, adjudicataris normalitzats (+detector de duplicats per NIF), duplicats de contractes, regles d'associació, alertes de venciment i revisions.
- **Migració de dades v1→v2 versió 1** + informe de reconciliació.

**Sortida:** paritat del 70% (tot el flux de dades); usuaris pilot en staging amb dades reals.

## Fase 2 — Organització, pla i integracions (3-4 setmanes)

- Departaments/empleats complets, LDAP endurit, mapejos AD. ✅ (2026-08-18, specs/ldap-auth.md: connector ldap amb filtres escapats i TLS obligatori, regles grup→rol/departament amb pantalla, provisió automàtica, fallback local)
- Pla anual de contractació (amb els bugs v1 corregits), favorits, superbuscador.
- Connector `gestiona` (autorització d'usuari + creació d'expedients redissenyada) i `smtp` (notificacions reals).
- **Tasques i recordatoris de contracte** (mòdul nou v2): calendari, assignacions, recordatoris per email/webhook, feed iCal, tasques proposades per les alertes.
- Webhooks sortints + service accounts/API keys (n8n operatiu contra la v2).
- Dashboard complet (incloent els KPIs calculats i mai mostrats a la v1).

**Sortida:** paritat funcional del 100% excepte IA.

## Fase 3 — Plataforma d'IA (4-5 setmanes)

- Provider layer + prompt registry + `ai_runs` + panell d'execucions.
- Agent CPV (pipeline híbrid + embeddings + feedback loop).
- Servei RAG (ingesta dels documents ja descarregats a fases anteriors).
- Redactor documental amb RAG real i export DOCX/PDF server-side.
- Agent auditor (red flags complets, incloent falta de concurrència) + informes programats.
- **Assistent legal**: motor de regles deterministes (llindars LCSP versionats per data d'efecte) + connector `boe` (normes consolidades, vigilància de canvis, re-indexació RAG) + revisió LLM de plecs amb citació d'articles.
- Agent analista (xat amb eines tancades) — pot lliurar-se com a beta.

**Sortida:** superioritat funcional sobre v1 en tot l'àmbit IA.

*Nota de seqüència dins la fase: el motor de regles determinista de l'assistent legal es pot avançar (no depèn de cap LLM) i dona valor immediat — p. ex. avisar d'un menor que supera els 15.000 € ja al moment de planificar-lo.*

## Fase 4 — Tall i estabilització (2 setmanes)

1. Congelació funcional de la v1; assaig final de migració amb cronometratge.
2. Cap de setmana de tall: migració definitiva, redirecció, v1 en només-lectura 1 mes.
3. Formació d'usuaris (guies per rol) i període d'hipervigilància (logs, mètriques, feedback).
4. Revisió de seguretat externa o autoavaluació ENS + pla d'accions.

## Riscos principals

| Risc | Mitigació |
|---|---|
| Canvis a les APIs de la Generalitat durant el projecte | connectors amb URLs/mapatges configurables; tests contra respostes gravades + smoke test diari contra API real |
| Dependència del flux Gestiona/n8n (contracte extern poc documentat) | fase 2 primerenca amb entorn de proves de Gestiona; conservar literalment el contracte v1 documentat a [08-hub-integracions.md](08-hub-integracions.md) §2.3 |
| Qualitat de la migració (dades brutes v1: duplicats, àlies) | script idempotent + informe de reconciliació + assajos repetits |
| Abast IA creix sense control | els agents es lliuren per fases darrere de flags de mòdul; quotes des del dia 1 |
| Equip petit vs. abast | les fases 1-2 són seqüencials i innegociables; la fase 3 és modular i retallable sense afectar la paritat |

## Definició de fet (per a cada fase)

- Endpoints al contracte OpenAPI amb exemples i scopes; contract tests verds.
- Tests d'autorització (matriu rol×acció) per a tot recurs nou.
- Auditoria d'esdeveniments per a tota escriptura nova.
- Documentació d'operació actualitzada (secrets, backups, runbooks de connector).
- **Specs sincronitzades**: specs mestres i de feature al dia, entrades de [BACKLOG.md](BACKLOG.md) de la fase tancades o reprioritzades — vegeu [11-metodologia-specs.md](11-metodologia-specs.md) §5.

## Nota sobre la planificació

Les fases són l'ordre previst, no un compromís tancat: el **backlog** és qui recull el que va sorgint i el triatge de final de fase decideix què entra a la següent. Quan una entrada de backlog canvia l'abast d'una fase, s'actualitza aquest document a la mateixa PR — el roadmap és una spec més i també se sincronitza.
