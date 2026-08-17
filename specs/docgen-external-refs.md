# Referencies externes al generador (SuperBuscador → projecte) (Estat: implementada)

## Context i objectiu

Peticio de l'Esteve (2026-08-17): poder afegir a un projecte del generador **documents d'expedients del SuperBuscador** (plecs d'altres ens) per aprofitar-los com a base. **La indexacio ha de ser temporal i nomes dins de l'ambit del projecte**: mai entra al corpus documental municipal ni apareix a la cerca general (coherent amb [[favorits-snapshot-no-contracts]]: el que es de fora no contamina les dades de l'ens).

## Comportament

### Model (migracio 0024)

- `project_documents`: `project_id` FK doc_projects CASCADE, `file_code`, `title`, `source_url`, `storage_key`, `status` (`pending|indexed|failed`), `error_detail`, `chunks_count`, `indexed_at`, `expires_at` (per defecte 30 dies des de la creacio).
- `project_chunks`: `project_id` (per a filtrar barat), `project_document_id` FK CASCADE, `chunk_index`, `content`, `embedding vector`. **Taula separada de `rag_chunks`**: la cerca general no la mira mai i es pot purgar sencera.

### Ingesta (job `docgen.index_external`)

Crida externa → sempre a la cua (regla del projecte). Payload `{project_document_id}`:
1. Descarrega el PDF amb el connector `pscp` (anti-SSRF per host i limit de mida ja existents).
2. El desa a l'object storage amb clau `projects/<project_id>/<uuid>.pdf`.
3. Extreu text (PyMuPDF), trosseja i genera embeddings (tasca `rag.embed`), desa a `project_chunks`, marca `indexed`.
Errors → `failed` amb detall visible a la UI (mai peta el job).

### Purga (job `docgen.purge_expired`, diari)

Esborra `project_documents` amb `expires_at < now()` (i els seus chunks per CASCADE) + el fitxer de l'storage. En esborrar un projecte, tot cau per CASCADE.

### Recuperacio

`doc_agent` combina, per a cada seccio: chunks dels documents locals de referencia (rag_chunks filtrat per document_id, com fins ara) **+** chunks del projecte (project_chunks filtrat per project_id). Les fonts citades distingeixen origen (`local` / `extern`, amb l'expedient d'origen).

### API i pantalles

- `POST /doc-projects/{id}/external-references` `{title, source_url, file_code?}` → crea el registre i encua el job (202).
- `DELETE /doc-projects/{id}/external-references/{ref_id}`.
- El detall del projecte inclou `external_references` amb estat i comptador de fragments.
- **SuperBuscador i Favorits**: l'explorador de fases (component compartit `PhaseExplorer`) es mostra a les dues pantalles; cada document te boto «＋ projecte» amb selector de projecte. Als favorits, les fases surten de les `phase_urls` guardades al snapshot (fusionades entre lots) — mai de les taules municipals.
- **Fitxa municipal** (ampliacio 2026-08-17): la pestanya Documents de `/contracts/:id` tambe te «＋ projecte» per document (mateix component; la referencia s'indexa temporalment al projecte via la URL publica del portal, com les altres fonts).
- El selector de projecte permet **crear un projecte al vol** (nom + «Crea»): crea el projecte i hi afegeix la referencia d'un sol gest. Simetricament, el boto «⭐ Desa» del SuperBuscador permet **crear una carpeta de favorits al vol**.
- **Generador**: el panell de referencies mostra les externes amb el seu estat (indexant / N fragments / error) i la data de caducitat.

### Pujada de PDFs propis (ampliacio 2026-08-17)

- `POST /doc-projects/{id}/external-references/upload` (multipart, camp `file`):
  PDF de l'ordinador de l'usuari, validat (extensio, capçalera %PDF, buit,
  limit 15 MB), desat directament a l'storage (`projects/<pid>/<uuid>.pdf`) i
  inserit a `project_documents` SENSE `source_url` (migracio 0027 la fa
  opcional). El job `docgen.index_external` salta la descarrega quan la fila
  ja te `storage_key` i indexa des de l'storage; mateixa caducitat i purga.
- UI: boto «Puja un PDF propi» al panell de referencies externes del projecte.

## Fora d'abast

- Renovacio automatica de la caducitat; OCR de PDFs escanejats; altres formats (DOCX).

## Criteris d'acceptacio

- [x] Afegir un document del SuperBuscador a un projecte l'indexa i queda disponible per a la redaccio.
- [x] Els seus fragments NO apareixen a la cerca RAG general ni al corpus municipal (test d'aillament).
- [x] Caducitat (30 dies) + job de purga diari; esborrat en cascada amb el projecte (test).
- [x] Botons a les dues pantalles; bateries verdes (416).
- [x] Els documents dels expedients guardats a Favorits tambe es poden dur a un projecte (ampliacio 2026-08-17).
- [x] «＋ projecte» i «⭐ Desa» permeten crear projecte/carpeta al vol (ampliacio 2026-08-17).
