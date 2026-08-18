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

### Accés obert de només lectura, vinculat a rol i abast (2026-08-18)

L'analista i el xat general poden consultar qualsevol dada o metadada de
CONTRACTES i ADJUDICATARIS, sempre dins de l'abast de qui pregunta:

- `data_schema`: cataleg de taules i columnes consultables — whitelist
  explicita de l'ambit contractes/adjudicataris (contracts, minor_contracts,
  contractors i satelits, cpv_codes, departments); MAI usuaris, sessions,
  credencials, parametres, xats, auditoria de seguretat ni metadades de
  sincronitzacio.
- `sql_select`: un unic SELECT lliure validat (sense comentaris ni `;`,
  paraules clau d'escriptura prohibides, identificadors sensibles bloquejats,
  totes les taules referenciades dins de la whitelist) executat en una
  transaccio READ ONLY amb statement_timeout de 5s i maxim 200 files.
  Doble tanca: validacio + transaccio de nomes lectura.
- **Abast per rol** (esmena de l'Esteve): admins i responsables de
  contractacio (abast global) ho poden consultar tot, SQL lliure inclos.
  Caps de departament i empleats amb can_audit (abast departamental):
  `sql_select`/`data_schema` DENEGATS (amb SQL lliure no es pot garantir el
  filtre), i les eines tancades filtren automaticament — search_contracts i
  aggregate nomes sobre contractes dels seus departaments
  (contract_departments), totals amb nota d'abast, red flags denegades
  (analisi de tot l'ens). L'abast l'injecta el bucle des de l'AuthzContext
  del cridador (mai el decideix el model) i no surt als passos visibles.

## Fora d'abast

- Conversa multi-torn; export a informe; consum extern via service accounts; scoping departamental de les eines.

## Criteris d'acceptacio

- [x] Bucle d'eines funcional amb proveidor real; steps visibles a la resposta.
- [x] Eines amb limits i parametres vinculats; sense permis → 403.
- [x] Pantalla /analyst; bateries verdes.
