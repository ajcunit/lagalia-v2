# Exportació de contractes (Estat: implementada)

## Context i objectiu

Quarta part de la F1-7 ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.4: «Exportació CSV (`;`, UTF-8 amb BOM) del conjunt filtrat»; [05-api.md](../docs/05-api.md)): exportar el llistat de contractes amb els filtres vigents a CSV o XLSX, generat **fora de la request** (job) i descarregat amb **token efímer d'un sol ús** (06 §2: mai un JWT per query string).

> ⚠️ DESVIACIÓ respecte a l'esbós de 05-api.md: la creació és `POST /contracts/exports` (crea un job; un GET amb efectes secundaris seria incorrecte). El GET queda per a la descàrrega.

## Comportament

Regles verificables:

- **`POST /contracts/exports`** — permís `contracts:export` (tots els rols, ✔ᴰ: l'export conté **només el que l'usuari veu**). Cos: `format` (`csv`|`xlsx`), `view` (`user`|`all`, validat com al llistat) i `filters` (mateixos filtres del llistat). Respon 202 amb el `Job` (`export.contracts`); l'abast efectiu es resol **a l'encuament** i viatja al payload — el job no re-avalua permisos.
- **Job `export.contracts`**: reutilitza el mateix predicat de visibilitat i filtres del llistat (una sola font de veritat al repositori), itera per lots, escriu a l'emmagatzematge (`exports/{job_id}.{ext}`) i deixa al resultat `{storage_key, filename, rows, format}`.
  - **CSV**: separador `;`, codificació UTF-8 **amb BOM** (paritat v1, obre bé a Excel).
  - **XLSX**: openpyxl, una fulla, capçalera congelada.
  - Columnes (ordre fix): expedient, lot, estat, estat intern, objecte, tipus, procediment, adjudicatari, NIF, import adjudicació, import licitació, publicat, inici, fi, fi calculada, departaments, alerta fi propera, possiblement finalitzat.
- **Descàrrega**: `POST /auth/ephemeral` amb `purpose: "download"` i `resource: <job_id>` (només si l'usuari pot llegir el job — el creador o rols amb `jobs:read_all`) → `GET /contracts/exports/{job_id}/download?token=…` **sense** capçalera d'autenticació: el token opac d'un sol ús (60 s, GETDEL) és l'autorització. Valida propòsit, recurs i que el job sigui `success`; serveix el fitxer amb `Content-Disposition`. Segona descàrrega amb el mateix token → 401.
- Auditoria: `contracts.export` (encuament) i `contracts.export_download` (descàrrega, amb el `user_id` del token).

## Canvis d'API

`openapi.yaml`: `POST /contracts/exports` (202 Job), `GET /contracts/exports/{id}/download` (binari, `security: []` amb token efímer). El propòsit `download` de `/auth/ephemeral` deixa de respondre 403.

## Canvis de dades

Cap. Dependència nova: `openpyxl`. L'emmagatzematge reutilitza `core/storage.py` (amb `get` afegit a la interfície).

## Seguretat i permisos

- L'export mai no amplia l'abast: el predicat de visibilitat es fixa a l'encuament amb l'abast efectiu del sol·licitant.
- Token de descàrrega d'un sol ús, 60 s, lligat a {usuari, propòsit, recurs}; mai el JWT de sessió per query string.
- El fitxer viu a l'emmagatzematge intern; no hi ha URL pública permanent.

## UI

- Llistat: botó **Exporta CSV** (visible per a tothom amb `contracts:export`) que encua l'export amb els filtres vigents, segueix el job (sondeig B-012) i, en acabar, demana el token i llança la descàrrega.

## Fora d'abast

- Exports de menors i adjudicataris (reutilitzaran el mateix job genèric).
- Neteja programada de fitxers d'export antics (jobs de manteniment, anotat).
- Stats i facets (F1-7e).

## Criteris d'acceptació

- [x] Export CSV amb `;` i BOM, columnes fixades, només l'abast de l'usuari (verificat amb usuari departamental).
- [x] XLSX vàlid amb les mateixes files.
- [x] Token de descàrrega d'un sol ús: la segona petició falla amb 401; token d'un altre recurs → 401.
- [x] Job visible amb progrés; auditoria d'encuament i descàrrega.
- [x] Bateries verdes; client TS regenerat.
