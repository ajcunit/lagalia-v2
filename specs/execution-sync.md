# Sincronització de la fase d'execució (dataset 8idu-wkjv) (Estat: implementada)

## Context i objectiu

B-017 (endpoint aportat per l'Esteve, 2026-08-17): el dataset obert
«Contractació pública a Catalunya: publicacions de la fase d'execució a la
PSCP» (`8idu-wkjv`) publica, per expedient i lot, les actuacions d'execució
(modificacions, pròrrogues, cessions, penalitats, resolucions…) amb tipus,
denominació, dates, import, adjudicatari, observacions i URL del JSON de
detall. Omple de veritat la pestanya «Execució» de la fitxa del contracte
(fins ara només pròrrogues/modificacions del dataset RPC).

## Comportament

### Model (migració 0028)

- `contract_executions`: `contract_id` FK contracts SET NULL (es vincula per
  file_code a la fila representativa; si el contracte s'esborra, el registre
  es conserva sense vincle), `file_code` (índex), `lot`, `action_type`,
  `action_name`, `date`, `end_date`, `amount`, `contractor_name`,
  `contractor_tax_id`, `observations`, `url_json`, `raw` JSONB,
  `content_hash` UNIQUE (dedup del registre font, que no té clau pròpia),
  `first_synced_at`/`last_synced_at`.
- Valor nou `execution` a l'enum `sync_kind`.

### Font `execution` al mapejador de camps

`EXECUTION_FIELDS` (sync_execution.py): defaults camp a camp del dataset
(`tipus_actuacio_execucio` → action_type, `denominacio_actuacio` →
action_name, `data`/`data_fi`, `import_sense_iva`, `identificacio`/
`denominacio` de l'adjudicatari, `observacions`, `url_json`), sobreescrivibles
a /admin/field-mappings com les altres fonts; remap local des del `raw`
(`sync.remap_execution`).

### Job `sync.execution` (manual + programable com la resta)

1. Consulta el dataset amb el query builder (filtre `codi_ine10` de l'ens).
2. Mapeja amb overrides; dedup per `content_hash` (unchanged si ja hi és).
3. Vincula el contracte per `file_code` (fila representativa, com les
   pròrrogues RPC); sense contracte local → es desa igualment amb
   `contract_id` NULL i es comptabilitza `unmatched` (l'expedient pot
   arribar en una sincronització posterior; el vincle es refà a cada sync).
4. `sync_run` amb comptadors i errors per registre, com el pipeline de
   referència.

### API i pantalla

- `GET /contracts/{id}/executions` (tag `contracts`, abast departamental com
  la resta de subrecursos): actuacions de l'expedient (per file_code, tots
  els lots), ordenades per data descendent.
- **Fitxa del contracte, pestanya Execució**: targeta «Actuacions d'execució
  (n)» amb tipus (badge), denominació, dates, import, adjudicatari i
  observacions; les pròrrogues i modificacions RPC es mantenen al costat.
  El comptador de la pestanya suma les tres coses.
- **Sincronitzacions** (/admin/sync): tipus nou `execution` al desplegable de
  llançament manual.

## Canvis d'API

`GET /contracts/{id}/executions` + `execution` al trigger de sync
(openapi.yaml + client TS regenerat).

## Seguretat

- Query builder SoQL per a tot filtre; abast departamental al subrecurs;
  cap escriptura fora del job.

## Fora d'abast

- Enriquiment del `url_json` de detall via connector pscp (com les fases);
  reconciliació automàtica amb les pròrrogues RPC duplicades; alertes per
  actuacions noves (webhooks).

## Criteris d'acceptació

- [x] Sync idempotent per hash amb vincle per file_code i unmatched comptats.
- [x] Font `execution` al mapejador amb overrides aplicats i remap local.
- [x] Subrecurs amb abast (404 fora d'abast); pestanya Execució amb les
  actuacions; bateries verdes.
