# Xat general i xat per expedient (Estat: implementada)

## Context i objectiu

B-016 (petició de l'Esteve, 2026-08-17): dues superfícies conversacionals
multi-torn amb historial persistent:

1. **Xat general** (`/chat`): conversa amb l'assistent sobre la contractació
   de l'ens — evolució de l'analista de dades (mateix bucle ReAct amb eines
   tancades) però amb memòria de conversa.
2. **Xat per expedient**: pestanya «Xat» a la fitxa del contracte; l'assistent
   té el context de l'expedient (dades, pròrrogues, modificacions, criteris,
   mesa) i els seus **documents indexats al RAG**, i cita les fonts.

## Comportament

### Model (migració 0026)

- `chat_threads`: `user_id` FK CASCADE, `scope` (`general|contract`),
  `contract_id` FK CASCADE nullable (obligatori si scope=contract), `title`
  (es fixa amb el primer missatge, truncat), timestamps.
- `chat_messages`: `thread_id` FK CASCADE, `role` (`user|assistant`),
  `content` TEXT, `sources` JSONB nullable (documents citats), `created_at`.
- **Propietat estricta per usuari** (com favorits): tota operació filtra per
  `user_id`; el fil d'un altre → 404. Les converses són privades (LOPD: el
  text lliure no es comparteix entre usuaris).

### Agents

- **General**: reutilitza el bucle de l'analista (`analyst_agent.answer_events`
  amb paràmetre nou `history`) — tasca `analyst.chat`, streaming
  step/thinking/delta. Ampliació 2026-08-18: a més de les eines tancades,
  pot consultar qualsevol dada o metadada de contractes i adjudicataris amb
  `data_schema` + `sql_select` (SELECT únic validat, transacció
  només-lectura), **vinculat al rol i a l'abast**: global per a admin/gestor;
  filtrat per departament per a la resta, amb SQL lliure denegat
  (vegeu ai-analyst.md).
- **Expedient** (`app/ai/chat_agent.py`, tasca nova `chat.contract`):
  1. Construeix `<expedient>` amb el resum del contracte (camps principals,
     pròrrogues, modificacions, criteris, mesa) — dades, no instruccions.
  2. Recupera fragments RAG **filtrats als documents d'aquell expedient**
     (`rag.search(document_ids=...)`) amb la darrera pregunta; emet
     `{"type":"sources"}` amb títol i fase dels documents usats.
  3. Streaming de la resposta amb citació («segons el PPT…»); historial del
     fil com a missatges previs.
  4. **Filtre per document** (ampliació 2026-08-17): `document_id` al cos del
     missatge acota la recuperació RAG a UN document de l'expedient (validat
     que hi pertany; límit de fragments més alt) i el model n'és informat.
     A la UI, selector «Pregunta sobre:» amb els documents indexats
     (`PhaseDocumentResponse.indexed` nou a l'API de documents del contracte).
- Guardrails habituals: comptabilitat a `ai_runs`, cap escriptura automàtica,
  resultats delimitats com a dades.

### API (tag `chat`; CRUD amb `tools:use` — material personal)

- `GET /chat/threads?scope=&contract_id=` — fils propis, més recents primer.
- `POST /chat/threads {scope, contract_id?}` — crea un fil (scope=contract
  exigeix contracte **visible** per abast departamental, si no 404).
- `GET /chat/threads/{id}` — fil + missatges.
- `DELETE /chat/threads/{id}` — esborra fil i missatges.
- `POST /chat/threads/{id}/messages/stream {content, document_id?}` — **streaming NDJSON**
  (fora d'openapi.yaml, convenció existent): persisteix el missatge d'usuari,
  executa l'agent amb l'historial, i persisteix la resposta sencera al final
  (amb `sources`). Autorització per àmbit del fil: general → `audit:run`
  (com l'analista); contract → `contracts:read` + contracte visible (404).

### Pantalles

- **/chat** (entrada «Xat» al menú, acció `audit:run`): barra lateral de
  converses (crear/esborrar), vista de conversa amb streaming markdown,
  indicador de raonament i passos d'eina desplegables (com l'analista).
- **Fitxa del contracte**: pestanya «Xat» amb el mateix component acotat a
  l'expedient; fonts citades visibles sota cada resposta.
- Component compartit `features/chat/ChatView.tsx`.

## Canvis d'API

CRUD de `/chat/threads` a openapi.yaml (+ client TS regenerat). L'endpoint
d'streaming segueix la convenció NDJSON fora del contracte.

## Seguretat

- Propietat per usuari amb 404 (mai 403 que confirmi existència); abast
  departamental aplicat al subrecurs contracte en crear i en cada stream.
- Cap eco del cos en errors; auditoria `chat.message` per stream completat.

## Fora d'abast

- Converses compartides per expedient (decisió LOPD pendent); retenció i
  purga automàtica (anirà amb B-006); xat sobre menors i plans.

## Criteris d'acceptació

- [x] Fil general multi-torn amb memòria (l'agent rep l'historial).
- [x] Fil d'expedient: context + RAG filtrat als documents del contracte,
  amb fonts citades.
- [x] Propietat: usuari B no veu els fils d'A (404); contracte fora d'abast → 404.
- [x] Streaming amb persistència del parell pregunta/resposta; bateries verdes.
