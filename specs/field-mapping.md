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

### Registre declaratiu i aplicació

- `MAPPABLE_FIELDS`: per a cada camp de destí, el camp font per defecte, el
  tipus de transformació (`text | amount | date | datetime | duration`) i
  l'etiqueta per a la UI. Camps compostos o d'identitat (file_code, status,
  lot, links, phase_urls, start/end calculats, content_hash, raw) **no són
  mapejables** i queden al codi.
- `map_contract(record, overrides=None)` i `contractor_fields(record,
  overrides=None)` resolen el camp font efectiu per a cada destí (override si
  n'hi ha, defecte si no). Els overrides es carreguen amb
  `field_mappings.get_overrides(session, source)`.
- S'apliquen a **tots els consumidors del mapeig**: job `sync.contracts`
  (carregats un cop per execució), proxy del SuperBuscador
  (`/public-registry/*`, per petició) i, per tant, als snapshots de favorits.

### Durada com a rang de dates (desviació documentada de l'A1 §3)

Si `durada_contracte` té la forma `dd/mm/aaaa a dd/mm/aaaa`, es mapeja com:
`start_date` = primera data, `end_date` = segona, `duration_months` = mesos
entre les dues (arrodonint la fracció ≥ 15 dies). El càlcul
formalització+durada només s'usa quan NO hi ha rang. Anotat a l'annex A1.

### Job `sync.remap_contracts`

Re-aplica el mapeig vigent sobre el `raw` guardat de cada contracte, **sense
cap crida externa**: actualitza els camps mapejables (mai la identitat
file_code/status/lot ni el contractista), historifica els canvis
(`contract_history`, change_type `sync`) i reporta comptadors. Encuat des de
la UI amb dedup.

### API (tag `config`; lectura `config:read`, escriptura `config:write`,
remap `sync:execute`)

- `GET /connectors/{slug}/field-mappings` — llista completa: destí, etiqueta,
  tipus, camp per defecte, camp efectiu i si està sobreescrit.
- `PUT /connectors/{slug}/field-mappings/{target_field}` `{source_field}` —
  desa l'override (valida destí conegut i `^[a-z0-9_]{1,80}$`); audita.
- `DELETE /connectors/{slug}/field-mappings/{target_field}` — restaura el
  defecte; audita.
- `GET /connectors/{slug}/field-mappings/sample?file_code=` — la fila `raw`
  guardada d'aquell expedient (per triar camps amb valors reals); 404 si no
  està sincronitzat. **Cap crida externa**: surt de `contracts.raw`.
- `POST /connectors/{slug}/actions/remap` — encua `sync.remap_contracts` (202).
- Només `socrata` és mapejable de moment; altres slugs → 404.

### Pantalla /admin/field-mappings (tessel·la «Mapatge de camps» al hub)

- Entrada d'expedient de mostra (es carrega la fila raw guardada): cada camp
  mostra el **valor real** que té a la font, tant del camp efectiu com dels
  candidats (datalist amb tots els camps del raw).
- Taula agrupada: etiqueta + camp BD, camp font editable amb datalist,
  defecte visible, marca «sobreescrit» + botó restaura, desa per fila.
- Botó «Re-aplica el mapeig a les dades guardades» (encua el remap, avís que
  també s'aplicarà a les properes sincronitzacions).

## Canvis d'API

Els cinc endpoints nous de dalt (openapi.yaml + client TS regenerat).

## Seguretat

- El `source_field` es valida amb patró estricte i NOMÉS s'usa com a clau de
  lectura del JSON retornat per la font (mai entra en cap consulta SoQL).
- La mostra surt de la BD local; sense token per query string; auditoria de
  cada canvi de mapeig (`config.field_mapping_updated` / `_reset`).

## Fora d'abast

- Mapejar transformacions noves des de la UI (el tipus és fix per camp);
  mapejadors per a altres fonts (Gestiona) quan arribin els connectors;
  mapeig per lot/fase diferenciat.

## Criteris d'acceptació

- [x] Override persistit s'aplica al sync, al SuperBuscador i al remap.
- [x] `durada_contracte` en format rang omple inici/fi/durada (cas 2885/2026).
- [x] Remap local re-omple camps a partir del raw guardat amb historial.
- [x] Pantalla amb valors reals de mostra; validació + auditoria; 403 sense
  permís; bateries verdes.
