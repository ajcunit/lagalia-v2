# Corpus normatiu BOE i revisio legal amb citacio (Estat: implementada)

## Context i objectiu

07 §3bis i 08 §2.6: connector `boe` que descarrega normes consolidades, les indexa per article al RAG i permet a l'assistent legal (capa 2) citar norma+article. Completa specs/compliance-rules.md (capa 1 determinista).

## Comportament

### Connector `boe` (hub, desactivat per defecte)

- Config: `base_url` (https://www.boe.es), `norm_ids` (llista d'identificadors BOE subscrits; per defecte LCSP `BOE-A-2017-12902`).
- Descarrega `GET /diario_boe/xml.php?id=<ID>`: XML consolidat amb `metadatos` (titol, rang, data, `fecha_actualizacion`) i `texto/p`. Sense credencials; TLS verificat.
- **Parsing per article**: els paragrafs es recorren i es tallen als encapçalaments `Artículo N`/`Disposición ...`; l'index inicial (encapçalaments consecutius sense cos) es descarta quedant-se amb el bloc de mes contingut per article.

### Model (migracio 0023)

- `legal_norms`: `boe_id UNIQUE`, `title`, `rank`, `published_at`, `consolidated_version` (fecha_actualizacion del BOE), `indexed_at`, `articles_count`.
- `legal_chunks`: `norm_id FK CASCADE`, `article_label` (p. ex. «Artículo 118»), `content`, `embedding vector`, UNIQUE(norm_id, article_label, chunk_index).

### Job `sync.boe_norms` (diari + manual)

- Per cada norma subscrita: descarrega, compara `consolidated_version`; si canvia (o `force`) → re-parseja, re-indexa (embeddings amb la tasca `rag.embed`) i emet `legal.norm_updated` a l'outbox (avis a admins/webhooks) marcant que cal revisar les regles deterministes afectades.

### Recuperacio en dues vies (millora sobre el disseny inicial)

El text a revisar es en catala i la norma en castella: nomes amb cosinus els articles clau no sortien. La capa 1 **sembra** la capa 2 — els articles que citen les regles deterministes (art. 118, art. 29...) es recuperen sempre per etiqueta, i s'hi afegeix la cerca hibrida (cosinus + full-text castella) del corpus.

### API i pantalla

- `GET /legal/norms` (estat de les normes: versio, articles, ultima comprovacio) i `POST /legal/norms/actions/sync` (`config:write`).
- `POST /compliance/review-text` `{text, subject_type?, subject_id?}` (`compliance:run`, **streaming NDJSON**): recupera els articles rellevants del corpus normatiu (cerca hibrida sobre legal_chunks) i executa la checklist de conformitat amb el LLM (tasca `legal.review`), **citant sempre norma i article**; persisteix a `compliance_reviews` amb `ai_run_id`.
- Pantalla: seccio «Corpus normatiu» a /admin/ai (normes, versio, boto sincronitza) i «Revisió legal amb IA» al generador documental (revisa el document redactat) i a /plan.

## Fora d'abast

- DOGC/Portal Juridic; alerta tematica de sumaris diaris; marca automatica de regles afectades (de moment nomes l'esdeveniment).

## Criteris d'acceptacio

- [x] LCSP descarregada (422 articles amb cos), parsejada i indexada (510 fragments) en viu.
- [x] Revisio d'un text citant norma+article, en streaming (verificat: menor de 32.000 € → ❌ amb cita «LCSP art. 118.1»).
- [x] Pantalles (corpus a /admin/ai, revisio al generador); bateries verdes.
