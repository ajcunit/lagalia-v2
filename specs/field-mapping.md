# Mapejador de camps font → base de dades (Estat: implementada)

## Context i objectiu

Petició de l'Esteve (2026-08-17): les dades de la fitxa d'un contracte poden
quedar mal mapejades quan el dataset canvia de format o el mapeig té un error
(cas real: `durada_contracte` de vegades arriba com a rang «15/06/2026 a
14/06/2027» i el 2885/2026 quedava sense inici/fi/durada). Cal poder **veure i
corregir manualment el mapeig camp a camp**, que quedi **persistit**, i poder
**re-aplicar-lo** a les dades ja sincronitzades sense tornar a demanar-les a la
font.

## Comportament

### Model (migració 0025)

`field_mappings`: `source` (slug del connector, p. ex. `socrata`),
`target_field` (camp del model v2), `source_field` (camp de la font),
`updated_by` FK users, timestamps; UNIQUE(source, target_field). **Només es
persisteixen els overrides**: els valors per defecte viuen al codi
(`MAPPABLE_FIELDS` a `app/integrations/socrata/mapping.py`, transcripció de
l'annex A1). Restaurar = esborrar la fila.

### Fonts mapejables (ampliació 2026-08-17: totes les fonts, no només Socrata)

| Font | Registre de defaults | Forma del camp font | Consumidors |
|---|---|---|---|
| `socrata` (dataset de contractes) | `MAPPABLE_FIELDS` + `CONTRACTOR_FIELDS` (mapping.py, annex A1) | camp pla del dataset | sync.contracts, proxy SuperBuscador, snapshots de favorits |
| `rpc` (registre únic: menors, pròrrogues, modificacions) | `RPC_FIELDS` (sync_rpc.py, specs/remaining-syncs.md) | camp pla del dataset RPC | sync.minor_contracts, sync.extensions |
| `pscp` (JSON de fases del portal, ~67 camps) | `PSCP_FIELDS` (extract.py, specs/pscp-enrichment.md) | **camí** dins del JSON: `a.b[0].c`, o `~text` per cerca heurística | enrich.contract/batch (escalars promocionats i enrichment) |

- Cada registre porta: camp/camí font per defecte, tipus (`text | amount |
  date | datetime | duration | int | bool | raw`), etiqueta per a la UI i,
  a pscp, les fases on aplica. Camps compostos o d'identitat (file_code,
  status, lot, links, phase_urls, start/end calculats, content_hash, raw)
  **no són mapejables** i queden al codi.
- `map_contract(record, overrides=None)`, `contractor_fields(...)`,
  `merge_minor_records(...)`, `extension_values(...)`,
  `modification_values(...)` i `extract_scalars(phase, payload, overrides)`
  resolen el camp font efectiu per destí. Els overrides es carreguen amb
  `field_mappings.get_overrides(session, source)` (un cop per job; per
  petició al proxy).
- Les dates-hora naïf del dataset es fixen explícitament a Europe/Madrid
  (són hores locals del portal); dependència `tzdata` per a Windows.

### Durada com a rang de dates (desviació documentada de l'A1 §3)

Si `durada_contracte` té la forma `dd/mm/aaaa a dd/mm/aaaa`, es mapeja com:
`start_date` = primera data, `end_date` = segona, `duration_months` = mesos
entre les dues (arrodonint la fracció ≥ 15 dies). El càlcul
formalització+durada només s'usa quan NO hi ha rang. Anotat a l'annex A1.

### Re-aplicar el mapeig a les dades guardades

- `sync.remap_contracts` (font socrata): re-mapa el `raw` de cada contracte
  **sense cap crida externa**; mai toca la identitat (file_code/status/lot)
  ni el contractista; **re-aplica la propagació de pròrrogues** sobre
  `calculated_end_date` (02 §2.8) perquè el remap no les trepitgi;
  historifica a `contract_history` (change_type `sync`).
- `sync.remap_rpc` (font rpc): re-mapa menors (des de `raw_award`/
  `raw_settlement`), pròrrogues i modificacions (des de `raw`), local.
- Font pscp: el «remap» encua `enrich.batch` amb `force` (els escalars surten
  del JSON viu del portal; crides externes, avisat a la UI).

### API (tag `config`; lectura `config:read`, escriptura `config:write`,
remap `sync:execute`)

- `GET /field-mappings/{source}` — llista completa: destí, etiqueta, tipus,
  camp per defecte, camp efectiu, si està sobreescrit i (pscp) fases.
- `PUT /field-mappings/{source}/{target_field}` `{source_field}` — desa
  l'override; valida destí conegut i patró per font (pla `^[a-z0-9_]{1,80}$`;
  pscp camí `^~?[a-zA-Z0-9_.\[\]]{1,200}$`); audita.
- `DELETE /field-mappings/{source}/{target_field}` — restaura el defecte; audita.
- `GET /field-mappings/{source}/sample?file_code=&phase=` — valors reals per
  triar camps: socrata (contracts.raw) i rpc (raw_award/raw_settlement o raw
  de pròrroga) **sense crides externes**; pscp descarrega el JSON de la fase
  indicada i el retorna **aplanat a camins** (`a.b[0].c`, els ~67 camps) —
  descàrrega puntual de diagnòstic, com el healthcheck.
- `POST /field-mappings/{source}/actions/remap` — encua el job de la font (202).
- Fonts reconegudes: `socrata`, `rpc`, `pscp`; qualsevol altra → 404.

### Pantalla /admin/field-mappings (tessel·la «Mapatge de camps» al hub)

- **Selector de font** (pestanyes): dataset de contractes / registre únic /
  JSON de fases; a pscp també selector de fase per a la mostra.
- Entrada d'expedient de mostra: cada camp mostra el **valor real** que té a
  la font, tant del camp efectiu com dels candidats (datalist amb tots els
  camps o camins del raw/JSON).
- Taula: etiqueta + camp BD + tipus (+ fases a pscp), camp font editable amb
  datalist, defecte visible, marca «sobreescrit» + botó restaura, desa per fila.
- Botó «Re-aplica el mapeig a les dades guardades» (encua el job de la font;
  a pscp avisa que re-executa l'enriquiment amb crides externes).

## Canvis d'API

Els cinc endpoints nous de dalt (openapi.yaml + client TS regenerat).

## Seguretat

- El `source_field` es valida amb patró estricte i NOMÉS s'usa com a clau de
  lectura del JSON retornat per la font (mai entra en cap consulta SoQL).
- La mostra surt de la BD local; sense token per query string; auditoria de
  cada canvi de mapeig (`config.field_mapping_updated` / `_reset`).

## Fora d'abast

- Mapejar transformacions noves des de la UI (el tipus és fix per camp);
  mapejador per a Gestiona quan arribi el connector; mapeig per lot
  diferenciat dins d'una mateixa fase pscp.

## Criteris d'acceptació

- [x] Override persistit s'aplica al sync, al SuperBuscador i al remap.
- [x] `durada_contracte` en format rang omple inici/fi/durada (cas 2885/2026,
  verificat en viu: 7.5k contractes recuperen dates).
- [x] Remap local re-omple camps a partir del raw guardat amb historial i
  re-aplica la propagació de pròrrogues.
- [x] Font `rpc`: overrides a menors/pròrrogues/modificacions + remap local.
- [x] Font `pscp`: overrides per camí als escalars promocionats; mostra del
  JSON de fase aplanat (~67 camps).
- [x] Pantalla amb selector de font i valors reals de mostra; validació +
  auditoria; 403 sense permís; bateries verdes.
