# 11 — Metodologia de desenvolupament: spec-driven

El projecte es desenvolupa amb **especificacions com a font de veritat** (spec-driven development). Regla d'or: **cap canvi existeix si no està a l'especificació** — el codi, les specs i la documentació viuen al mateix repositori i es mouen junts.

## 1. Jerarquia d'especificacions

| Nivell | Artefacte | Rol |
|---|---|---|
| 1 | `docs/rebuild/01..10` | **Specs mestres**: visió, funcional, arquitectura, dades, API, seguretat, IA, integracions, roadmap, UI. Defineixen el *què* i el *perquè* |
| 2 | `openapi.yaml` | **Spec executable** del contracte API: la CI verifica que el codi la compleix (cap deriva possible) |
| 3 | `specs/<feature>.md` | **Spec de funcionalitat**: una per peça de treball no trivial (plantilla a §4). Concreta el *com* abans d'escriure codi |
| 4 | `docs/rebuild/BACKLOG.md` | **Backlog viu**: tot el que sorgeix durant el desenvolupament entra aquí abans d'anar enlloc més |

Les migracions Alembic, els esquemes JSON de capacitats de connectors i les regles de compliment versionades també són specs executables: es revisen com a documentació.

## 2. El cicle de sincronització

```
     idea / necessitat / troballa durant el desenvolupament
                        │
                        ▼
              ┌──────────────────┐
              │   BACKLOG.md     │  triatge: prioritat + esbós de solució
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  spec (nivell    │  s'actualitzen les specs mestres afectades
              │  1-3 afectades)  │  i s'escriu/actualitza la spec de feature
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  codi + tests    │  a la MATEIXA pull request que la spec
              └────────┬─────────┘
                       ▼
              backlog: entrada marcada Fet, amb enllaç a la PR
```

### Regles de sincronització

1. **Regla de la mateixa PR**: una PR que canvia comportament ha de contenir el canvi de spec corresponent (mestra, de feature o OpenAPI). Una PR que canvia una spec sense codi és vàlida (fase de disseny); el contrari no.
2. **El canvi pot néixer a qualsevol banda, però es tanca a tot arreu**: si un hotfix o una descoberta tècnica obliga a desviar-se de la spec, la mateixa PR actualitza la spec (o, si és gran, crea l'entrada de backlog i marca la secció de la spec amb `> ⚠️ DESVIACIÓ: vegeu BACKLOG#id` — mai una desviació silenciosa).
3. **OpenAPI no pot derivar mai**: el contract testing a CI (schemathesis + oasdiff contra el `openapi.yaml` versionat) falla la build si el codi i el contracte divergeixen. És la sincronització automàtica; la resta és disciplina + revisió.
4. **Les specs mestres es mantenen consolidades**: quan diverses specs de feature toquen el mateix àmbit, el seu contingut es refon a la spec mestra corresponent i la spec de feature es marca com a implementada (les mestres descriuen sempre l'estat actual + el previst, mai historial de canvis — per això hi ha git).

### Mecanismes que ho fan complir (no només disciplina)

- **Plantilla de PR** amb checklist obligatòria: *specs afectades actualitzades? / OpenAPI tocat i regenerat el client? / entrada de backlog enllaçada? / migració + model + doc de dades coherents?*
- **CODEOWNERS**: canvis a `docs/rebuild/**` i `openapi.yaml` requereixen revisió del responsable funcional.
- **CI**: contract testing (regla 3), lint d'enllaços interns de les specs, i un check que rebutja PRs amb canvis a `app/modules/**` sense cap canvi a `specs/**`, `docs/**` o `openapi.yaml` (override explícit amb etiqueta `no-spec-change` per a refactors purs).
- **Revisió assistida per IA**: pas de CI opcional on un agent (Claude Code) compara el diff de codi amb les specs afectades i comenta discrepàncies — encaixa amb l'orientació a agents del projecte.

## 3. El backlog

Fitxer únic i versionat: [BACKLOG.md](BACKLOG.md). Tot hi entra: idees, deute tècnic, desviacions, peticions d'usuaris, troballes de desenvolupament.

**Camps de cada entrada:**

| Camp | Valors |
|---|---|
| ID | `B-nnn` seqüencial (estable, per referenciar des de specs i PRs) |
| Títol i descripció | què i per què |
| Prioritat | `P1` (bloqueja fase en curs) · `P2` (propera fase) · `P3` (millora, quan es pugui) |
| Com desenvolupar-la | esbós de solució: enfocament, specs mestres afectades, riscos, estimació de mida (S/M/L) |
| Estat | `Proposta → Triada → Especificada → En curs → Feta` (o `Descartada`, amb el motiu) |
| Enllaços | spec de feature, PRs, entrada de roadmap |

**Cicle de triatge**: revisió curta setmanal (o en tancar cada fase del roadmap): es prioritza, s'escriu el "com desenvolupar-la" i es decideix si entra a la fase en curs, al roadmap o s'espera. Res no s'implementa directament des de `Proposta`.

## 4. Plantilla de spec de feature (`specs/<feature>.md`)

```markdown
# <Feature>  (BACKLOG: B-nnn · Estat: proposta|aprovada|implementada)

## Context i objectiu     — per què, per a qui, què resol
## Comportament           — regles funcionals verificables (Given/When/Then on aporti)
## Canvis d'API           — endpoints/esquemes nous o modificats (delta d'openapi.yaml)
## Canvis de dades        — taules/columnes + pla de migració
## Seguretat i permisos   — scopes, abast departamental, auditoria
## UI                     — pantalles/patrons afectats (ref. 10-ui.md)
## Specs mestres a actualitzar — llista explícita (02 §x, 04 §y...)
## Fora d'abast           — què NO fa
## Criteris d'acceptació  — checklist verificable (base dels tests E2E)
```

## 5. Definició de fet (amplia la del roadmap)

Una feina només està **Feta** quan: codi + tests verds, spec de feature en estat `implementada`, specs mestres i `openapi.yaml` actualitzats, client TS regenerat, entrada de backlog tancada amb enllaç a la PR, i — si toca — migració i runbook d'operació actualitzats.
