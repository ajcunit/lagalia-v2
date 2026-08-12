# Annex A1 — Mapeig del connector Socrata (Transparència Catalunya)

Transcripció literal del mapeig implementat a la v1 (`SyncService.map_api_to_model`). **Aquesta taula és l'especificació del connector**: la v2 s'ha de poder construir sense consultar el codi de la v1.

Dataset: `https://analisi.transparenciacatalunya.cat/resource/ybgg-dgi6.json` (contractes majors), filtrat per `codi_ine10`.

## 1. Camps directes

| Camp origen (API Socrata) | Camp destí v1 | Camp destí v2 |
|---|---|---|
| `codi_expedient` | `codi_expedient` | `file_code` |
| `codi_ine10` | `codi_ine10` | `ine10_code` |
| `codi_dir3` | `codi_dir3` | `dir3_code` |
| `objecte_contracte` | `objecte_contracte` | `subject` |
| `tipus_contracte` | `tipus_contracte` | `contract_type` |
| `procediment` | `procediment` | `procedure` |
| `tipus_tramitacio` | `tipus_tramitacio` | `processing_type` |
| `denominacio_adjudicatari` | `adjudicatari_nom` | → `contractors.canonical_name` (via àlies) |
| `identificacio_adjudicatari` | `adjudicatari_nif` | → `contractors.tax_id` |
| `adjudicatari_nacionalitat` | `adjudicatari_nacionalitat` | → `contractors.nationality` |
| `nom_organ` | `organisme_adjudicador` | `awarding_body` |
| `departament_adjudicador` | `departament_adjudicador` | `awarding_department` |
| `numero_lot` | `lots` | `lot` |
| `codi_cpv` | `cpv_principal_codi` | `cpv_code` |
| `cpv_principal_descripcio` | `cpv_principal_descripcio` | `cpv_description` |
| `codi_nuts` / `descripcio_nuts` | idem | `nuts_code` / `nuts_description` |
| `forma_financament` | `forma_financament` | `financing` |
| `data_actualitzacio` | `data_actualitzacio` | `updated_at_source` |
| `durada_contracte` | `durada_contracte` (parsejat, §3) | `duration_months` |

## 2. Camps amb renom o derivació

| Regla | Origen | Destí |
|---|---|---|
| **Estat**: primer valor no buit | `resultat` \|\| `fase_publicacio` | `estat_actual` / `status` |
| `valor_estimat_contracte` | → | `preu_licitar` / `tender_amount` |
| `import_adjudicacio_sense` | → | `preu_adjudicar` / `award_amount` **i també** `import_licitar_sense_iva` (duplicitat de la v1: revisar a la v2) — *resolució v2: es descarta la duplicitat, només `award_amount` ([contracts-sync.md](../../specs/contracts-sync.md))* |
| `import_adjudicacio_amb_iva` | → | `import_adjudicacio_amb_iva` / `award_amount_vat` |
| `pressupost_licitacio_sense` | → | `pressupost_licitacio_sense_iva` / `budget_no_vat` |
| `pressupost_licitacio_sense_1` | → | `pressupost_licitacio_sense_iva_expedient` |
| `pressupost_licitacio_amb` | → | `pressupost_licitacio_amb_iva` / `budget_vat` |
| `pressupost_licitacio_amb_1` | → | `pressupost_licitacio_amb_iva_expedient` |
| `valor_estimat_expedient` | → | `valor_estimat_expedient` / `estimated_value` |
| `data_publicacio_anunci` | → | `data_publicacio` / `published_at` |
| `data_formalitzacio_contracte` | → | `data_formalitzacio` / `formalized_at` |
| `data_adjudicacio_contracte` | → | `data_anunci_adjudicacio` / `award_notice_date` |
| `data_publicacio_anul` | → | `data_anulacio` / `cancellation_date` |
| `data_anunci_previ`, `data_anunci_licitacio`, `data_anunci_formalitzacio` | directes | notice dates |

## 3. Camps calculats (no vénen de l'API)

```
durada_mesos = parse_duration(durada_contracte)
data_inici   = data_formalitzacio + 1 dia
data_final   = data_formalitzacio + durada_mesos + 1 dia      (= data_finalitzacio_calculada)
alerta_finalitzacio  = avui <= data_final <= avui + mesos_alerta
possiblement_finalitzat = data_final < avui
```

**`parse_duration(valor)`** — el camp pot venir com a número o com a text tipus `"1 anys 0 mesos 0 dies"`:
1. Si es pot convertir a número directament → aquest valor és el nombre de mesos.
2. Si no, extreu amb expressions regulars els grups `(\d+)\s*any`, `(\d+)\s*mes`, `(\d+)\s*di`.
3. `total = anys*12 + mesos + (1 si dies > 15 altrament 0)`.
4. Retorna `null` si el total és 0.

Els càlculs només s'apliquen si hi ha `data_formalitzacio` **i** durada; altrament els camps queden nuls.

## 4. Camps que poden arribar com a objecte

`enllac_publicacio` i els nou `url_json_*` (`futura`, `agregada`, `cpm`, `previ`, `licitacio`, `avaluacio`, `adjudicacio`, `formalitzacio`, `anulacio`) poden arribar com a string **o** com a objecte `{"url": "..."}`. Cal normalitzar-ho sempre a string. A la v2 van dins `links` i `phase_urls` (JSONB).

## 5. Enllaços directes

`enllac_anunci_previ`, `enllac_licitacio`, `enllac_adjudicacio`, `enllac_formalitzacio`, `enllac_perfil_contractant`, `url_plataforma_contractacio` → `links` (JSONB) a la v2.

## 6. Àlies d'adjudicatari

Abans de desar, `denominacio_adjudicatari` es substitueix pel nom canònic si existeix una entrada d'àlies (`contractor_aliases`). El nom original es conserva a `raw_contractor_name` per a traçabilitat (millora v2).

## 7. Clau natural i detecció de canvis

- Upsert per (`codi_expedient`, `estat_actual`, `lots`) → v2: (`file_code`, `status`, `lot`).
- `hash_contenido` = MD5 del JSON complet ordenat (v2: SHA-256 a `content_hash`). Si difereix → actualització camp a camp + entrada d'historial `sync`.

## 8. Regles d'associació automàtica (implementació v1)

Regles actives ordenades per `prioridad` descendent; la primera que casa assigna departament. Camps avaluables: `departament_adjudicador`, `organisme_adjudicador`, `objecte_contracte`, `cpv_principal_codi`. Operadors implementats: `igual` (igualtat exacta), `contiene` (subcadena, case-insensitive), `comienza_con` (prefix, case-insensitive).

> ⚠️ El model v1 declara també els operadors `mayor_que`/`menor_que` i el tipus `importe`, però **no estan implementats**. La v2 els ha d'implementar o eliminar-los del model ([04-model-de-dades.md](../04-model-de-dades.md) §2).

## 9. Altres datasets del mateix connector

| Ús | Recurs | Filtre |
|---|---|---|
| Pròrrogues i modificacions | `hb6v-jcbf` | `id_organisme_contractant`, opcionalment `codi_expedient`; discriminació per `situaci_contractual` (conté "pròrroga" → pròrroga; conté "modificaci" → modificació) |
| Contractes menors + liquidacions | `hb6v-jcbf` | `id_organisme_contractant` + `procediment_adjudicacio = 'Menor'`; agrupació per expedient i fusió dels registres d'adjudicació i liquidació |
| Diccionari CPV | `wxdw-5eyv` | cap; upsert dels 4 nivells (`cpv_divisi`, `cpv_grup`, `cpv_classe`, `cpv_categoria`) amb jerarquia per `padre_codigo` |
