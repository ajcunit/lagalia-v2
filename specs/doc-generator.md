# Redactor documental — fase 1: projectes, index i redaccio amb RAG (Estat: implementada)

## Context i objectiu

07 §2.3 i 04 §6: correccio del defecte principal v1 (seccions redactades sense mirar les referencies). Projectes amb 3 documents (PPT, PPA, INFORME), referencies del corpus indexat, index proposat per IA, redaccio per seccio amb recuperacio RAG **citant les fonts**, edicio manual i export DOCX server-side.

## Comportament

### Model (migracio 0022; 04 §6 adaptat)

- `doc_projects`: user_id (propietat estricta com favorits: 404 si no es teu), name, reference_doc_ids JSONB (ids de phase_documents indexats — el «cartipas» del projecte).
- `doc_documents`: project_id FK CASCADE, doc_type (`PPT|PPA|REPORT`), sections JSONB `[{title, instructions, content_md, sources}]`, UNIQUE(project_id, doc_type). Es creen buits amb el projecte.
- ⚠️ DESVIACIO de 04 §6: `doc_exports` (registre d'exports amb storage_key) es difereix — l'export DOCX es genera i es descarrega al moment, sense persistir; si cal historial d'exports, B-nnn.

### API (accio `tools:use`, propietat per usuari; tag `docgen`)

- `GET/POST /doc-projects`, `GET/PATCH/DELETE /doc-projects/{id}` (amb documents inclosos al detall).
- `GET /doc-references?q=` — cerca de documents indexats (per titol o expedient) per triar referencies; `PUT /doc-projects/{id}/references` `{document_ids}` (valida que estiguin indexats).
- `POST /doc-projects/{id}/documents/{doc_type}/actions/generate-index` — tasca `doc.index`: proposa seccions a partir de fragments representatius de les referencies (JSON validat; fallback a plantilla fixa de 5-7 seccions per tipus si el JSON falla).
- `PATCH /doc-projects/{id}/documents/{doc_type}` — desa seccions (edicio manual: afegir/treure/reordenar/canviar contingut).
- `POST /doc-projects/{id}/documents/{doc_type}/sections/{index}/actions/draft/stream` — tasca `doc.section` en **streaming NDJSON** (thinking/delta/sources/done): recupera els chunks mes rellevants NOMES de les referencies del projecte (cosinus+trigram filtrat per document_id), redacta en catala amb to legal i **cita les fonts** (expedient + document); en acabar desa el contingut a la seccio (esborrany editable, el control huma es l'edicio i l'export).
- `GET /doc-projects/{id}/documents/{doc_type}/export.docx` — DOCX real server-side (python-docx): titol, seccions amb encapçalaments i contingut (paragrafs del Markdown pla), peu amb fonts. Descarrega autenticada per capçalera (fetch+blob, cap token per query).

### Pantalla /generator (zona Intel·ligencia, «Generador documental»)

- Llista de projectes propis + alta; vista de projecte: cercador de referencies (afegir/treure), pestanyes PPT/PPA/Informe, boto «Proposa l'index», editor de seccions (titol, instruccions, contingut Markdown amb render), boto «Redacta amb IA» per seccio (streaming amb indicador de raonament), fonts mostrades sota cada seccio, i «Exporta a Word».

## Fora d'abast

- Agent revisor (07 §2.3.4); plantilles d'index administrables; export PDF; doc_exports persistits; cartipas global multi-pantalla (les referencies es trien al projecte; el boto «envia al cartipas» des de fitxes/SuperBuscador arribara amb el cartipas global).

## Criteris d'acceptacio

- [x] Projecte amb referencies reals, index proposat i seccio redactada citant fonts del corpus (verificat en viu amb el PPT/PCAP de l'expedient 2744/2026).
- [x] Propietat estricta; seccions editables; DOCX valid descarregable.
- [x] Tasques doc.index i doc.section configurables per perfil/model.
- [x] Bateries verdes.
