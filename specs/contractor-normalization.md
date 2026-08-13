# Normalització d'adjudicataris i duplicats agrupats per NIF (Estat: implementada)

## Context i objectiu

Resol B-011. El primer sync real va confirmar la brutícia de la font: un mateix NIF amb fins a **53 variants de nom** (puntuació, majúscules, «S.L» vs «S.L.»), que creaven un contractor per variant i feien esclatar els parells de duplicats de manera quadràtica (8.481 pendents — irrevisables un a un). Tres peces:

1. les variants **trivials** s'adjunten com a àlies a la ingesta (mai més un contractor nou per una coma);
2. una **consolidació** única de les dades existents que fusiona automàticament les variants trivials del mateix NIF;
3. la revisió humana passa de parells a **grups per NIF** (un grup = un cas) amb fusió en bloc.

## Comportament

### Normalització (`contractors/normalize.py`)

- `normalize_name(nom)`: minúscules, sense accents, sense puntuació, espais col·lapsats i **formes societàries eliminades al final del nom** — abreujades (SL, SLU, SA, SAU, SCCL… amb o sense punts) i escrites senceres («SOCIEDAD LIMITADA», «SOCIETAT ANÒNIMA»…). Només per a **comparació**: mai s'escriu el nom normalitzat.
- `identity_key(nom)`: la normalització **sense espais**, per a comparació DINS del mateix NIF («OFF-SHORE» vs «OFFSHORE» són la mateixa empresa amb seguretat perquè el NIF ja coincideix). És la clau que fan servir la ingesta i la consolidació.
- Dos noms amb la mateixa clau són la **mateixa identitat** (variant trivial); si difereixen, són noms genuïnament diferents i toca revisió humana.

### Ingesta (`resolve_contractor`)

- Mateix NIF i nom nou: si `normalize_name(nou) == normalize_name(canònic)` (o coincideix amb un àlies existent normalitzat), el nom s'adjunta com a **àlies** del contractor existent i es reutilitza. Només un nom genuïnament diferent crea contractor propi (i, per tant, parell de duplicat a la detecció).

### Consolidació de dades existents (job `contractors.consolidate`)

- Agrupa els contractors per NIF; dins de cada NIF, les variants amb la mateixa normalització es **fusionen automàticament** al membre amb més contractes vinculats (les altres esdevenen àlies, refs transferides — reutilitza `merge_contractors`).
- En acabar, re-executa la detecció de parells: només queden parells entre noms genuïnament diferents.
- Auditoria `contractors.consolidate` amb comptadors. És una regla determinista de dades (cap sortida d'IA): no requereix acceptació per variant.

### Revisió agrupada (API + UI)

- `GET /contractors/duplicates/groups` (permís `duplicates:manage`): grups de contractors amb el mateix NIF i parells pendents, ordenats per mida del grup; cada membre amb id, nom, comptadors i volum. Paginació per cursor (offset).
- `POST /contractors/duplicates/groups/resolve` — cos `{tax_id, action: merge|reject, canonical_id?}`:
  - `merge`: tots els membres del NIF es fusionen al `canonical_id` triat (obligatori); els parells pendents del grup desapareixen amb la fusió. Auditoria `contractors.merge_group`.
  - `reject`: tots els parells pendents del grup es marquen `rejected` (noms diferents legítims sota el mateix NIF).
- **UI** `/contractors/duplicates`: la pestanya «Pendents» mostra **grups** (NIF, membres amb volum, radi per triar el canònic, botons *Fusiona-ho tot* i *Rebutja el grup*, amb confirmació); les pestanyes de resolts continuen mostrant parells. La resolució de parells individuals es manté a l'API (compatibilitat).

## Canvis d'API

`openapi.yaml`: `GET /contractors/duplicates/groups`, `POST /contractors/duplicates/groups/resolve`; esquema `ContractorDuplicateGroup`. Client TS regenerat.

## Canvis de dades

Cap migració. La consolidació modifica dades (fusions) amb rastre d'auditoria.

## Seguretat i permisos

- Tot sota `duplicates:manage` (admin, resp. contractació); fusions auditades amb el detall de perdedors.

## Fora d'abast

- Similaritat difusa entre NIFs diferents (trigram sobre noms); només mateix NIF.

## Criteris d'acceptació

- [x] `normalize_name` cobreix els patrons reals (casos de la BD als tests).
- [x] Ingesta: variant trivial → àlies, mai contractor nou; nom genuí → contractor + parell.
- [x] Consolidació: variants trivials fusionades automàticament; els parells pendents es redueixen; re-run idempotent.
- [x] Grups per NIF amb fusió en bloc i rebuig de grup; parells individuals intactes.
- [x] Bateries verdes; consolidació executada sobre les dades reals amb informe.
