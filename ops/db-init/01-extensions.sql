-- Extensions requerides pel model de dades (docs/04-model-de-dades.md).
-- S'executen una sola vegada, en crear el volum de la base de dades.

-- Cerca vectorial per al RAG (rag_chunks.embedding).
CREATE EXTENSION IF NOT EXISTS vector;

-- Cerca difusa i per similitud: adjudicataris, descripcions CPV, objectes de contracte.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Correu electrònic insensible a majúscules (users.email).
CREATE EXTENSION IF NOT EXISTS citext;
