# CLAUDE.md — Instruccions del projecte LAGALia v2

Context per a qualsevol agent d'IA (o persona nova) que treballi en aquest repositori.

## Què és això

Plataforma de gestió de contractació pública de l'Ajuntament de Cunit. És una
**reescriptura completa** d'una aplicació anterior (FastAPI + React) amb quatre
eixos: API first, seguretat per disseny, agents d'IA i hub d'integracions.

L'aplicació antiga **no és aquí** i no és la referència: tot el comportament que
cal reproduir està transcrit a `docs/` (especialment `docs/02-especificacio-funcional.md`
i els annexos `docs/annexos/`).

## Regla número u: spec-driven

**Cap canvi de comportament existeix si no està a l'especificació.** El codi, les
specs i `openapi.yaml` viuen junts i es mouen junts.

- Abans d'implementar res: llegeix la spec afectada. Si no n'hi ha, escriu-la
  (`specs/<feature>.md` a partir de `specs/_TEMPLATE.md`) i fes-la aprovar.
- Una PR que canvia comportament **ha d'incloure** el canvi de spec corresponent.
  Una PR només de spec és vàlida; codi sense spec, no.
- Si has de desviar-te d'una spec, actualitza-la a la mateixa PR o marca-hi
  `> ⚠️ DESVIACIÓ: vegeu BACKLOG B-nnn`. Mai una divergència silenciosa.
- Tot el que sorgeixi pel camí (idea, deute tècnic, dubte) va a `docs/BACKLOG.md`
  amb prioritat i esbós de solució. No s'implementa res que estigui en estat
  `Proposta`.

Detall complet: `docs/11-metodologia-specs.md`.

## Documents que has de conèixer

| Si toques… | Llegeix primer |
|---|---|
| Qualsevol cosa | `docs/README.md` i `docs/11-metodologia-specs.md` |
| Comportament funcional | `docs/02-especificacio-funcional.md` |
| Estructura, mòduls, jobs | `docs/03-arquitectura.md` |
| Base de dades i migracions | `docs/04-model-de-dades.md` |
| Endpoints | `docs/05-api.md` + `openapi.yaml` |
| Autenticació, permisos, secrets | `docs/06-seguretat.md` + `docs/annexos/A2-matriu-permisos.md` |
| Agents d'IA, prompts, RAG | `docs/07-agents-ia.md` + `docs/annexos/A3-prompts-ia.md` |
| Connectors i sincronitzacions | `docs/08-hub-integracions.md` + `docs/annexos/A1-mapeig-socrata.md` |
| Frontend | `docs/10-ui.md` |

## Convencions

**Idioma**: codi, noms de fitxer, identificadors, rutes d'API i missatges de
commit en **anglès**. Interfície d'usuari i documentació en **català**. No barregis
castellà i català als identificadors (era el problema de l'aplicació antiga).

**Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic.
Estructura per mòduls (`app/modules/<domini>/`) amb routers prims → serveis
d'aplicació → repositoris. Cap regla de negoci al router.

**Frontend**: React 18 + TypeScript + Vite + TanStack Query + Tailwind. El client
HTTP **es genera** des d'`openapi.yaml`; no s'escriu a mà.

**Migracions**: sempre Alembic. Mai `CREATE TABLE`/`ALTER TABLE` a l'arrencada
de l'aplicació.

## Prohibicions explícites

Aquestes regles existeixen perquè van ser vulnerabilitats reals de l'aplicació
anterior (`docs/06-seguretat.md` §2). Hi ha lint de seguretat a CI que les detecta:

- ❌ `verify=False` en cap client HTTP. Si un certificat intern falla, es
  configura el CA bundle.
- ❌ SQL amb interpolació de cadenes (`text(f"...")`, f-strings dins consultes).
  Sempre paràmetres vinculats.
- ❌ Consultes a APIs externes amb filtres construïts per concatenació (SoQL,
  LDAP): sempre a través del query builder del connector, amb validació d'entrada.
- ❌ `if user.role == ...` dins d'un router. L'autorització va pel motor central
  (`Authorize(action)`), i l'abast departamental s'aplica **també als detalls i
  subrecursos**, no només als llistats.
- ❌ Secrets a la resposta d'una API, a logs o a payloads de webhook. Els valors
  marcats com a secrets són d'escriptura only (`is_set: true` a la lectura).
- ❌ Tokens per query string. Per a SSE i descàrregues, token efímer d'un sol ús.
- ❌ Eco del cos de la petició en respostes d'error o logs.
- ❌ Crides a serveis externs dins d'una request d'usuari: van a la cua de jobs.
- ❌ Escriptures automàtiques a partir de sortides d'IA sense acceptació humana
  registrada.

## Abans de donar per feta una tasca

1. Tests verds (unitaris, integració i contract testing contra `openapi.yaml`).
2. Spec de la feature en estat `implementada` i specs mestres al dia.
3. `openapi.yaml` actualitzat si l'API canvia + client TS regenerat.
4. Migració Alembic si el model canvia, coherent amb `docs/04-model-de-dades.md`.
5. Entrada de `docs/BACKLOG.md` tancada amb enllaç a la PR (si venia d'allà).
6. Auditoria: tota escriptura nova ha de deixar rastre a `audit_log`.

## Notes de context

- Administració pública catalana: l'accessibilitat **WCAG 2.1 AA** és obligació
  legal (RD 1112/2018), no una millora opcional.
- Dades personals mínimes (nom, correu, DNI). El DNI es xifra.
- L'aplicació antiga continuarà en producció durant la construcció; qualsevol
  canvi de format de dades ha de ser compatible amb el script de migració.
