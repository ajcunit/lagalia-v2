# Servei RAG compartit — fase 1: ingesta i cerca (Estat: implementada)

## Context i objectiu

07 §3: corpus de documents de fase (184 PDFs ja a MinIO; `phase_documents.indexed_at` preparat) → extraccio de text → chunking → embeddings → recuperacio hibrida. Fonament del redactor documental i de la capa 2 de l'assistent legal.

## Comportament

- **Deps**: `pymupdf` (extraccio), `pgvector` (tipus SQLAlchemy). Migracio 0021: `CREATE EXTENSION vector` + `rag_chunks` (document_id FK phase_documents CASCADE, contract_id, chunk_index, content TEXT, embedding `vector` sense dimensio fixa — corpus petit, escaneig exacte; dimensio+index HNSW quan el model d'embeddings quedi fixat — , UNIQUE(document_id, chunk_index)).
- **providers.embed(profile, texts, model?)**: openai_compatible POST /embeddings i ollama POST /api/embed; registrat a ai_runs (task rag.embed). Tasca `rag.embed` al registre (configurable per perfil/model, p. ex. nomic-embed-text a Ollama o un model d'embeddings al vLLM).
- **Job `rag.index`** (arq): documents amb storage_key i indexed_at NULL (o force) → bytes de MinIO → text amb PyMuPDF → chunks ~3.200 caracters amb solapament 300 respectant paragrafs → embeddings en lots → insercio + indexed_at. Errors per document a sync_item_logs? No: log estructurat + document saltat (reintent al seguent run).
- **Cerca hibrida** `rag_search(query)`: cosinus (`embedding <=> query_embedding`) + trigram sobre content, fusio simple per rang; retorna chunk, document (titol, fase, doc_type) i contracte (file_code).
- **API**: `GET /rag/status` (docs indexats/pendents, chunks) i `POST /rag/actions/index` (encua el job; `sync:execute`); `POST /rag/search` `{query, limit≤10}` (`tools:use`).
- **Pantalla**: seccio «RAG documental» a /admin/ai — estat (indexats/pendents/chunks), boto «Indexa els documents» i caixa de cerca de prova amb resultats (chunk + font).

### Tria de fases a descarregar i indexar (ampliacio 2026-08-18, peticio de l'Esteve)

- Setting `rag.indexable_phases` (llista JSON; buit/no definit = totes):
  nomes els documents de les fases marcades (licitacio, adjudicacio,
  formalitzacio…) es descarreguen (copia local) i s'indexen al RAG; la resta
  queden a la fitxa nomes amb l'enllac al portal. S'aplica a l'enriquiment
  (les copies ja descarregades es conserven).
- `GET /rag/phases` (config:write): fases del repositori amb comptadors
  (total, amb copia, indexats) per alimentar la checklist.
- UI: pestanya RAG de /admin/ai (la pantalla ara va per pestanyes:
  Proveidors · Tasques · RAG · Corpus BOE · Execucions), amb checklist per
  fase (noms traduits), boto de desar i drecera «totes les fases».
- De passada, fix de `collect_documents`: les claus d'idioma (ca/es/en/oc) ja
  no trepitgen el `doc_type` (abans tot quedava com a «ca»); el tipus real es
  refresca amb l'enriquiment i queda disponible per a usos futurs.

## Fora d'abast

- Redactor documental (seguent PR, consumira rag_search); corpus normatiu BOE (3bis); re-indexacio automatica subscrita a esdeveniments (job programat n'hi haura prou de moment).

## Criteris d'acceptacio

- [x] Job d'ingesta idempotent (verificat amb dobles; la indexacio real espera un perfil amb model d'embeddings configurat a la tasca rag.embed).
- [x] rag_search hibrida retorna passatges amb la font.
- [x] Seccio a /admin/ai amb estat, indexacio i cerca de prova.
- [x] Bateries verdes.
