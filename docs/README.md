# Paquet de re-arquitectura — LAGALia v2

Documents per reconstruir des de zero l'aplicació de gestió de contractació pública, amb paritat funcional total i quatre eixos nous: **API first**, **seguretat per disseny**, **plataforma d'agents d'IA** (anàlisi de dades i generació documental) i **hub d'integracions**.

Elaborat a partir de l'anàlisi exhaustiva del codi actual (backend FastAPI: 15 routers, 16 serveis, ~30 taules; frontend React: 28 pàgines) — agost 2026.

| # | Document | Contingut |
|---|---|---|
| 00 | [Primers passos](00-primers-passos.md) | Arrencada del repositori, ordre de les primeres PR, comprovació de fi de Fase 0 |
| 01 | [Visió i principis](01-visio-i-principis.md) | Objectius, principis rectors, mètriques d'èxit, abast |
| 02 | [Especificació funcional](02-especificacio-funcional.md) | Inventari complet v1 (rols, 18 mòduls, regles de negoci crítiques, defectes a no reproduir) + mòduls nous v2 (tasques i recordatoris) |
| 03 | [Arquitectura](03-arquitectura.md) | Monòlit modular: API core, plataforma IA, hub, jobs/esdeveniments, stack, estructura de codi |
| 04 | [Model de dades](04-model-de-dades.md) | Esquema PostgreSQL v2 (+pgvector), normalitzacions, pla de migració v1→v2 |
| 05 | [API](05-api.md) | Convencions API-first, authn/scopes, mapa complet de recursos, esdeveniments |
| 06 | [Seguretat](06-seguretat.md) | Model d'amenaces, 18 debilitats v1 → correcció estructural, authz centralitzada, secrets, ENS/RGPD |
| 07 | [Agents d'IA](07-agents-ia.md) | Orquestrador, 4 agents (CPV, auditor, redactor, analista), RAG, traçabilitat i guardrails |
| 08 | [Hub d'integracions](08-hub-integracions.md) | Connectors (Socrata, PSCP, Gestiona, LDAP, SMTP, webhooks), jobs, guia d'extensió |
| 09 | [Roadmap](09-roadmap.md) | 5 fases (~4 mesos), migració de dades, riscos, definició de fet |
| 10 | [Interfície d'usuari](10-ui.md) | Sistema de disseny, navegació, patrons d'interacció, accessibilitat WCAG 2.1 AA |
| 11 | [Metodologia spec-driven](11-metodologia-specs.md) | Com es treballa: specs com a font de veritat, sincronització spec↔codi, backlog i definició de fet |
| — | [BACKLOG.md](BACKLOG.md) | **Document viu**: tot el que sorgeix durant el desenvolupament, amb prioritat i com desenvolupar-ho |

**Annexos** (transcripcions del comportament v1 perquè cap spec depengui del codi antic):

| Annex | Contingut |
|---|---|
| [A1 — Mapeig Socrata](annexos/A1-mapeig-socrata.md) | Camp a camp de l'API de Transparència Catalunya, càlculs de dates, parsing de durada, regles d'associació |
| [A2 — Matriu de permisos](annexos/A2-matriu-permisos.md) | Acció × rol × abast departamental; base del motor d'autorització i dels seus tests |
| [A3 — Prompts d'IA](annexos/A3-prompts-ia.md) | Prompts literals v1 i pipeline híbrid de classificació CPV amb les seves puntuacions |

**Com llegir-lo:** 00 (per on començar) → 11 (com treballem) → 01 → 02 (què fem) → 03-05 (com es construeix) → 06-08 i 10 (eixos transversals) → 09 (quan).

**Regla del projecte:** aquests documents són l'especificació viva, no una foto inicial. Tota PR que canvia comportament actualitza la spec corresponent a la mateixa PR; tot el que sorgeix pel camí passa primer pel backlog. Detall a [11-metodologia-specs.md](11-metodologia-specs.md).
