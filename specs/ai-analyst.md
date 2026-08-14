# Agent analista de dades (Estat: implementada)

## Context i objectiu

07 §2.5: preguntes en llenguatge natural sobre el corpus de contractacio, respostes amb les dades reals adjuntes (mai xifres del model). Primer agent amb bucle d'eines.

## Comportament

- **Eines tancades** (`app/ai/analyst_tools.py`, mai SQL lliure; tot amb parametres vinculats i limits):
  - `search_contracts(q?, year?, contract_type?, limit≤10)` — cerca a contracts (ILIKE escapat).
  - `aggregate(group_by ∈ {year, contract_type, department, contractor}, metric ∈ {count, sum_award}, year_from?, year_to?)` — top 20.
  - `get_red_flags()` — totals + top 3 per bloc (reutilitza risk_audit).
  - `totals()` — comptadors globals (contractes, menors, adjudicataris, imports).
- **Bucle ReAct amb JSON** (agnostic de proveidor, sense dependre del tool-calling natiu): el model respon `{"tool": nom, "args": {...}}` o `{"answer": markdown}`; maxim 6 iteracions; resultats d'eina injectats delimitats com a dades no fiables. Si esgota iteracions → resposta amb el que tingui. Tasca `analyst.chat` (configurable per perfil/model).
- `POST /ai/analyses` `{question}` → `{answer_markdown, steps: [{tool, args, rows}]}` — la UI ensenya les dades font de cada pas (07: «respostes sempre amb la taula/dades font adjunta»). Sincron interactiu; registrat a ai_runs (una fila per iteracio LLM).
- **Permis**: `audit:run` (admins i can_audit) — l'agent veu agregats de tot l'ens, com la pantalla de red flags. Ampliar a mes rols quan hi hagi scoping per departament a les eines (backlog).

### Pantalla /analyst (zona Intel·ligencia, «Analista de dades», accio audit:run)

- Pregunta → resposta en Markdown + desplegable «dades consultades» per pas (eina, parametres, taula de files). Exemples clicables per començar.

## Fora d'abast

- Conversa multi-torn; export a informe; consum extern via service accounts; scoping departamental de les eines.

## Criteris d'acceptacio

- [x] Bucle d'eines funcional amb proveidor real; steps visibles a la resposta.
- [x] Eines amb limits i parametres vinculats; sense permis → 403.
- [x] Pantalla /analyst; bateries verdes.
