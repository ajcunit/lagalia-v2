# Syncs de pròrrogues, menors i CPV (Estat: implementada)

## Context i objectiu

Quarta PR de la Fase 1: els tres jobs restants del flux de dades ([08-hub-integracions.md](../docs/08-hub-integracions.md) §3) sobre els datasets d'A1 §9. Com que la documentació no conservava el mapeig camp a camp del dataset RPC, **aquesta spec el fixa a partir de l'esquema real verificat contra l'API (2026-08-12)** — sondes sobre els registres de Cunit.

## Esquema real verificat (font de veritat d'aquesta spec)

Dataset RPC `hb6v-jcbf`, filtre `id_organisme_contractant` (que **coincideix amb el codi INE10**; es reutilitza `org.ine10_code`):

| Camp | Present a | Ús v2 |
|---|---|---|
| `codi_expedient` | tots | clau de casament amb `contracts.file_code` / `minor_contracts.file_code` |
| `situaci_contractual` | tots | discriminador: conté «pròrroga» → pròrroga; conté «modificaci» → modificació; `menor` → adjudicació de menor; conté «liquidaci» → liquidació |
| `contracte`, `descripcio_expedient` | tots | descripció del menor |
| `adjudicatari` | tots | nom (⚠️ **el dataset no té NIF**: resolució per nom/àlies) |
| `import_adjudicacio`, `data_adjudicacio`, `exercici` | tots | import/data/exercici |
| `anys_durada`, `mesos_durada`, `dies_durada` | tots | durada del menor |
| `tipus_contracte`, `procediment_adjudicacio`, `numero_lot`, `lot_desert`, `codi_cpv` | tots/parcial | metadades |
| `numero_prorroga`, `data_inici_prorroga`, `data_fi_prorroga` | files de pròrroga | `extensions` |
| `data_liquidacio`, `import_liquidacio`, `tipus_liquidacio` | files de liquidació | liquidació del menor |

Dataset CPV `wxdw-5eyv`: cada fila porta **la jerarquia completa** (`cpv_divisi/descripci_divisi`, `cpv_grup/…`, `cpv_classe/…`, `cpv_categoria/…`) — *desviació respecte d'A1 §9, que parlava de `padre_codigo`: el pare es deriva de la mateixa fila*.

## Comportament

Regles verificables:

- **`sync.extensions`** (kind `extensions`): recorre el RPC de l'ens i discrimina per `situaci_contractual` (case/accent-insensitive). Pròrrogues → upsert d'`extensions` per (contracte, `numero_prorroga`); modificacions → `modifications` (cap mostra real a Cunit: mapeig mínim amb `raw` complet, revisable). El casament és per `file_code`: la fila s'adjunta al contracte representant (id més antic) i la **data de fi es propaga a totes les files de l'expedient** (`calculated_end_date` = `data_fi_prorroga` si és posterior) amb historial `sync` — el recàlcul O(n²) de la v1 desapareix (una sola passada). Expedients sense contracte → `sync_item_logs` (`unmatched`), run `partial` no (és esperat: els menors també hi són); comptador informatiu.
- **`sync.minor_contracts`** (kind `minor`): filtre servidor `procediment_adjudicacio = 'Menor'`; agrupació per `codi_expedient` i **fusió del registre d'adjudicació i el de liquidació** (02 §2.5); upsert per `file_code` amb comparació camp a camp (new/updated/unchanged); adjudicatari resolt per nom (àlies → canònic; sense NIF, mai s'inventa); `raw_award`/`raw_settlement` conservats.
- **`sync.cpv`** (kind `cpv`): cada fila upserta els 4 nivells amb `parent_code` derivat (divisió ← grup ← classe ← categoria) i nivell mapejat a l'enum (`Division|Group|Class|Category`); re-run íntegre → `unchanged`.
- Tots tres: `sync_run` amb comptadors i estat, progrés observable, `dedup_key` propi, i errors per registre a `sync_item_logs` sense tombar el run.
- L'encadenament automàtic extensions-després-de-contracts i el cron configurable arriben amb la programació (fora d'abast aquí; el scheduler manté només el heartbeat).

## Canvis d'API

Cap (el `POST /sync-runs` arriba amb l'API de sync).

## Canvis de dades

Cap migració: tot cap a taules de la 0004.

## Seguretat i permisos

Com `sync.contracts`: cap SoQL fora del builder, TLS verificat, `raw` conservat per traçabilitat.

## Fora d'abast

- Enriquiment pscp (PR F1-7), alertes (`alerts.recompute`).
- Cron configurable i encadenament de jobs.
- NIF de menors: no existeix a la font; el rànquing unificat casa per contractor resolt per nom (B-011 en millorarà la qualitat).

## Criteris d'acceptació

- [x] Pròrroga real casada amb el seu contracte: `extensions` creada i `calculated_end_date` propagada amb historial.
- [x] Menor amb adjudicació+liquidació fusionats en una fila; re-run → `unchanged`; canvi → `updated`.
- [x] CPV: 4 nivells amb jerarquia correcta d'una sola fila; re-run → `unchanged`.
- [x] Discriminador robust a accents/majúscules.
- [x] Syncs reals executats contra l'API (pròrrogues, menors i CPV de Cunit).
- [x] `ruff`, `mypy --strict` i tota la suite verds.
