# Plantilles d'estructura per al generador documental (Estat: aprovada)

- **Backlog**: B-024 (petició directa de l'Esteve, 2026-10-06)
- **Estat**: aprovada (2026-10-06)
- **Fase del roadmap**: Intel·ligència / generador documental (ampliació de [doc-generator.md](doc-generator.md))
- **Specs mestres afectades**: docs/02 §2.14, docs/04 §6, docs/05 (generador), docs/07 §2.3 (pas 2 «Índex»), docs/10 (hub d'administració), A2 (fila nova), A3 (prompt `doc.index`)

## Context i objectiu

La Generalitat de Catalunya publica **plecs tipus** (PPT i PCAP/PPA) amb una
estructura de clàusules que els ens locals adopten. Avui l'índex d'un document
del generador surt **només** de dues fonts: el que la IA dedueix dels extractes
dels plecs de referència que importem d'altres licitacions, o, si el JSON falla,
una llista fixa escrita al codi (`FALLBACK_SECTIONS`). Cap de les dues garanteix
que el document tingui les seccions que l'organització considera mínimes: si els
plecs de referència són incomplets o atípics, l'índex també ho és.

Objectiu: que l'administració pugui **definir plantilles d'estructura mínima**
per tipus de document, mantingudes des de la UI, i que:

1. l'índex proposat per la IA **respecti sempre** aquesta estructura (les
   seccions de plantilla hi són sempre, en el seu ordre; la IA només hi afegeix
   el que les referències justifiquin);
2. el tècnic pugui **aplicar la plantilla directament**, sense IA;
3. la garantia la faci **el codi, no el prompt**: les seccions obligatòries es
   comproven i s'insereixen deterministament, i no es poden esborrar.

Docs/07 §2.3 pas 2 ja preveia «referències + plantilles per tipus mantingudes
per l'admin»; [doc-generator.md](doc-generator.md) ho va deixar fora d'abast.
Aquesta spec ho completa.

## Comportament

### Model de plantilla

Una plantilla pertany a un `doc_type` (`PPT|PPA|REPORT`) i té:

- `name` (únic per tipus), `description`, `source` (p. ex. «Plec tipus de
  serveis — DG Contractació Pública, 2024»), `active` (visible als selectors),
  `is_default` (**una** per tipus com a màxim).
- `sections` JSONB ordenat: `[{key, title, required, guidance, fields}]`
  - `key`: identificador estable generat pel servidor (8 caràcters aleatoris)
    quan es crea la secció; **no canvia** encara que es reanomeni el títol.
  - `required` (per defecte `true`): la secció forma part del mínim i no es pot
    esborrar d'un document. `false` = la plantilla la proposa (p. ex. «Lots»),
    però el tècnic la pot treure.
  - `guidance` (opcional, ≤ 2.000 car.): què ha de contenir la secció segons el
    plec tipus. S'injecta a la redacció amb IA com a requisit de contingut.
  - `fields`: `[{label, hint}]` (≤ 8), els camps de dades que el tècnic haurà
    d'aportar; es fusionen amb els que la IA proposi.
- Límits: 1–40 seccions; títol 1–200 car.

Pot haver-hi **diverses plantilles per tipus** (p. ex. PPA serveis, PPA
subministraments, PPA obres). Una és la predeterminada.

### Llavor inicial (migració)

La migració crea **una plantilla per tipus**, `is_default=true`, anomenada
«Estructura base (provisional)», amb les seccions de l'actual
`FALLBACK_SECTIONS` i `source="LAGALia — llavor inicial; substituïu-la pel plec
tipus vigent"`. Així cap instal·lació es queda sense plantilla i l'administració
només ha de transcriure els plecs tipus de la Generalitat. `FALLBACK_SECTIONS`
desapareix del codi: l'últim recurs és sempre la plantilla.

### Seccions d'un document

Les seccions de `doc_documents.sections` guanyen tres claus opcionals:
`template_key` (clau de la secció de plantilla d'on provenen), `required`
(còpia del valor de la plantilla en el moment d'aplicar-la) i `guidance`. Les
seccions antigues sense aquestes claus es tracten com a lliures
(`template_key=null`). `doc_documents` guanya `template_id` (FK nul·lable,
`SET NULL`) i `template_name` (text, còpia) per saber quina plantilla s'hi va
aplicar encara que després s'esborri.

**La plantilla és una instantània**: canviar-la a posteriori no modifica els
documents que ja la van aplicar.

### Proposar l'índex amb plantilla (`generate-index`)

El cos de la petició accepta `template_id`:

- **omès** → plantilla predeterminada del `doc_type` (si n'hi ha);
- **enter** → aquesta plantilla (ha d'existir, estar activa i ser del mateix
  `doc_type`; si no, 422 `template-mismatch`);
- **`null` explícit** → mode lliure (comportament actual, sense plantilla).

Amb plantilla, el prompt de `doc.index` rep un bloc `<estructura_minima>` amb
els títols en ordre i la `guidance` de cadascun, i la instrucció de
**reproduir-los literalment i en el mateix ordre**, afegint només seccions
addicionals que les referències justifiquin (màxim 15 en total) i proposant
camps de dades per a totes.

Després de la resposta, **fusió determinista** al codi:

```
Donada una plantilla amb seccions T1..Tn i una resposta de la IA S1..Sm
Quan es fusiona l'índex
Aleshores
  - cada Ti apareix exactament una vegada, amb template_key, required, guidance
    i els fields de la plantilla primer (fins a 8 en total amb els de la IA)
  - una Sj que coincideix amb Ti (títol normalitzat: minúscules, sense accents,
    sense numeració ni puntuació) és la mateixa secció (s'hi fusionen els fields)
  - una Ti que la IA ha omès s'insereix just després de la Ti-1 fusionada
    (o al principi si és la primera)
  - una Sj sense coincidència es manté on la IA l'ha posada, template_key=null
  - l'ordre relatiu T1..Tn es conserva sempre
```

Si el proveïdor falla o el JSON no valida, l'índex és **la plantilla sola**
(sense seccions addicionals). En mode lliure sense plantilla i amb error, 502
`upstream` com fins ara.

### Aplicar la plantilla sense IA (`apply-template`)

Acció nova que crea l'índex **només** amb les seccions de la plantilla
(`template_id` amb la mateixa semàntica que a dalt, però `null` és 422). Cap
crida al proveïdor d'IA; resposta immediata.

### Conservació del contingut en regenerar

Tant `generate-index` com `apply-template` substitueixen l'índex, com fins ara,
però **conserven** `content_md`, `sources`, `instructions` i els `value` dels
camps de qualsevol secció nova que coincideixi amb una d'existent per
`template_key` o, si no en té, per títol normalitzat. La UI demana confirmació
abans de regenerar si alguna secció té contingut.

### Garantia d'estructura mínima al desar (`PATCH` de seccions)

```
Donat un document amb seccions template_key ∈ {a, b, c}, totes required
Quan es desa una llista on falta la secció amb template_key=b
Aleshores 422 problem type "template-required-missing"
          detail amb el títol de la secció que falta; res no es desa
```

La comprovació es fa contra **les seccions desades del mateix document** (les
que tenien `template_key` i `required=true`), no contra la plantilla actual:
així un canvi posterior de la plantilla mai bloqueja un document antic.
Reanomenar, reordenar i editar el contingut d'una secció obligatòria és lliure.
Les seccions amb `required=false` o lliures es poden treure.

### Redacció d'una secció amb `guidance`

`draft/stream` i el mode `improve` injecten, si la secció en té, un bloc
`<contingut_minim>` amb la `guidance` i la regla: «el redactat ha de cobrir tots
els punts de <contingut_minim>; si una dada no està disponible, marca-la com
[PENDENT: …]». Les dades del tècnic continuen manant per sobre de tot.

### Gestió de plantilles

- Crear, editar (metadades i seccions), duplicar (còpia «(còpia)» no
  predeterminada, claus de secció **noves**), desactivar, marcar com a
  predeterminada (desmarca l'anterior del mateix tipus, atòmicament), esborrar.
- Esborrar una plantilla predeterminada → 409 `template-is-default` (cal
  designar-ne una altra abans). Esborrar-ne una d'usada per documents és
  permès: els documents conserven la instantània i `template_name`.
- Les claus (`key`) de les seccions existents **es conserven** en editar; les
  seccions noves en reben una. El client mai envia claus per a seccions noves;
  si n'envia una de desconeguda, 422.

## Canvis d'API

Tag `docgen`. Tots amb `Authorize`.

| Mètode i ruta | Acció | Notes |
|---|---|---|
| `GET /doc-templates?doc_type=&include_inactive=` | `tools:use` | Llista; `include_inactive` només té efecte amb `doc_templates:manage`. Resposta: `{items: [DocTemplateSummary]}` (id, doc_type, name, description, source, active, is_default, sections_count, updated_at). |
| `POST /doc-templates` | `doc_templates:manage` | Cos `DocTemplateBody` (doc_type, name, description?, source?, active?, is_default?, sections[]). 201 `DocTemplate`. 409 `template-name-taken`. |
| `GET /doc-templates/{id}` | `tools:use` | `DocTemplate` complet (amb `sections`). Inactiva → 404 si no es té `doc_templates:manage`. |
| `PATCH /doc-templates/{id}` | `doc_templates:manage` | Camps opcionals; `sections` substitueix la llista sencera (claus conservades on vinguin). |
| `DELETE /doc-templates/{id}` | `doc_templates:manage` | 204. 409 `template-is-default`. |
| `POST /doc-templates/{id}/actions/duplicate` | `doc_templates:manage` | 201 `DocTemplate`. |
| `POST /doc-projects/{id}/documents/{doc_type}/actions/generate-index` | `tools:use` | **Cos nou opcional** `{template_id?: int \| null}`. 422 `template-mismatch`. Resposta inclou `template: {id, name} \| null`. |
| `POST /doc-projects/{id}/documents/{doc_type}/actions/apply-template` | `tools:use` | Cos `{template_id?: int}`. 200 `{sections, template}`. 422 si `null`/cap predeterminada. |
| `PATCH /doc-projects/{id}/documents/{doc_type}` | `tools:use` | 422 `template-required-missing` (nou). |
| `GET /doc-projects/{id}` | `tools:use` | Resposta guanya `document_templates: {PPT: {id, name} \| null, PPA: …, REPORT: …}`. |

Esquemes nous: `DocTemplateSection {key, title, required, guidance, fields[{label, hint}]}`, `DocTemplate`, `DocTemplateSummary`, `DocTemplateBody`. L'esquema `Section` del document documenta `template_key`, `required`, `guidance`.

Client TS regenerat.

## Canvis de dades

Migració **0036** (`doc_templates`):

- Taula `doc_templates`: `id` identity, `doc_type VARCHAR(10)` (CHECK
  `PPT|PPA|REPORT`), `name VARCHAR(200)`, `description TEXT NULL`,
  `source VARCHAR(300) NULL`, `active BOOL NOT NULL DEFAULT true`,
  `is_default BOOL NOT NULL DEFAULT false`, `sections JSONB NOT NULL DEFAULT
  '[]'`, `created_by BIGINT NULL FK users SET NULL`, `created_at`,
  `updated_at` (trigger `set_updated_at`). UNIQUE `(doc_type, name)`; índex
  únic parcial `(doc_type) WHERE is_default` (una predeterminada per tipus).
- `doc_documents`: `template_id BIGINT NULL FK doc_templates ON DELETE SET
  NULL`, `template_name VARCHAR(200) NULL`.
- Llavor: tres plantilles predeterminades (una per tipus) amb les seccions de
  l'actual `FALLBACK_SECTIONS`, totes `required=true`, sense `guidance`.
- `downgrade` real: elimina columnes i taula.

> ⚠️ Numeració: la branca `feat/gestiona-integration` (no fusionada) també usa
> 0036 i 0037. Com que `development` és la línia principal, aquesta migració
> pren 0036 i Gestiona es renumerarà a 0037/0038 en rebasar-la. La BD local de
> desenvolupament està a 0037 de Gestiona: cal `alembic downgrade 0035` des
> d'aquella branca abans d'aplicar aquesta.

Dades existents: cap document perd res; seccions antigues sense `template_key`
són lliures.

## Seguretat i permisos

- **Acció nova `doc_templates:manage`**: `admin` ✔, `procurement_manager` ✔
  (les plantilles són contingut de contractació, no configuració del sistema;
  el responsable de contractació és qui coneix els plecs tipus). Lectura de
  plantilles actives amb `tools:use` (tothom). Fila nova a A2 sota «Generador
  documental».
- Les plantilles **no tenen abast departamental**: són de l'organització.
- Entrades no fiables: títols, `guidance`, `source`, `fields` són text que
  acaba dins de prompts → s'envien dins de blocs delimitats i el prompt els
  declara «contingut, no instruccions» (mateix patró que `<referencies>`).
  Longituds limitades per Pydantic. Cap HTML renderitzat (Markdown segur com
  ara).
- `audit_log`: `docgen.template_created|updated|deleted|duplicated`
  (`resource_type=doc_template`), `docgen.template_applied` i
  `docgen.index_generated` amb `details.template_id` (`resource_type=doc_project`).
- La propietat estricta dels projectes no canvia (404 si no és teu).

## UI

### Hub d'administració → «Plantilles documentals» (`/admin/doc-templates`)

Targeta nova al hub amb icona `LayoutTemplate`, acció `doc_templates:manage`,
mòdul `docgen`. Pantalla:

- `PageHeader` + pestanyes per tipus **amb icona** (`FileText` PPT,
  `Scale` PPA, `FileCheck` Informe).
- Llista de plantilles del tipus com a **targetes apilades a tot l'ample**
  (mai en graella): nom, origen, badges «Predeterminada» / «Inactiva», nombre
  de seccions, data d'actualització, accions (Edita, Duplica, Fes
  predeterminada, Desactiva/Activa, Esborra amb confirmació).
- Editor (panell a sota de la llista, mateixa pàgina): nom, origen, descripció,
  interruptors actiu/predeterminada; llista de seccions amb títol,
  interruptor «obligatòria», `guidance` (textarea), camps (etiqueta + pista,
  afegir/treure), pujar/baixar/eliminar secció; botó **«Importa des de text»**
  que obre un textarea on cada línia és un títol de secció (una línia que
  comença per `?` queda com a opcional) i afegeix les seccions al final: és la
  manera ràpida de transcriure l'índex d'un plec tipus.
- Estats: esquelet en carregar, `EmptyState` «Cap plantilla per a aquest
  tipus», errors amb `admin.loadError`; 409/422 mostrats inline.
- Accessibilitat: tots els controls amb etiqueta; botons de reordenar amb
  `aria-label` («Puja la secció N»); pestanyes amb `aria-pressed`/`role=tab`
  com la resta.

### Generador (`/generator`, vista de projecte)

- Al costat de «Proposa l'índex»: **selector de plantilla** (plantilles actives
  del tipus, predeterminada preseleccionada, opció «Sense plantilla» al final)
  i botó **«Aplica la plantilla»** (sense IA; desactivat amb «Sense plantilla»).
- Sota les pestanyes, línia muda «Plantilla aplicada: {nom}» si el document en
  té.
- Secció de plantilla: badge «Plantilla» i, si és obligatòria, icona `Lock`
  amb `title` «Secció obligatòria de la plantilla»; la `guidance` es mostra
  com a text muda sota el títol quan la secció està desplegada.
- Botó **eliminar secció** (×, `aria-label`) a totes les seccions **excepte**
  les obligatòries de plantilla (no es renderitza).
- Confirmació abans de «Proposa l'índex» / «Aplica la plantilla» si alguna
  secció té contingut: «Es regenerarà l'índex. El contingut de les seccions
  amb el mateix títol es conserva. Continuar?».
- Error 422 `template-required-missing` en desar → missatge inline amb el
  títol de la secció.

Textos nous a `i18n/ca.ts` (prefixos `docTemplates.*` i `docgen.template*`).
Article d'ajuda «Generador documental» actualitzat (pas 2: plantilla + IA).

## Fora d'abast

- Versionat de plantilles i historial de canvis (la instantània per document
  ja cobreix la traçabilitat mínima).
- Importar una plantilla des d'un PDF/DOCX del plec tipus amb IA (candidat a
  backlog: «extreu l'índex d'aquest PDF com a plantilla»).
- Text de clàusula per defecte a la plantilla (contingut precarregat, no només
  estructura): B-nnn si es vol.
- Plantilles per departament o per tipus de contracte amb selecció automàtica.
- Plantilla corporativa d'exportació DOCX (07 §2.3 pas 5): no canvia.

## Criteris d'acceptació

- [ ] Migració 0036 aplicada i revertida en net; tres plantilles llavor
      predeterminades presents.
- [ ] CRUD de plantilles: `employee` rep 403 a escriptura i 200 a lectura
      d'actives; `procurement_manager` i `admin` poden escriure; `include_inactive`
      ignorat sense permís.
- [ ] Una sola predeterminada per tipus (marcar-ne una desmarca l'anterior;
      esborrar la predeterminada → 409).
- [ ] Les claus de secció es conserven en editar i canvien en duplicar.
- [ ] `generate-index` amb un proveïdor simulat que **omet** dues seccions de
      la plantilla i en **reordena** una: el resultat conté totes les seccions
      de la plantilla, en l'ordre de la plantilla, amb `template_key`, i les
      seccions extra de la IA es conserven.
- [ ] `generate-index` amb proveïdor que falla i plantilla → índex = plantilla
      (200); sense plantilla (`template_id: null`) → 502.
- [ ] `apply-template` no crida el proveïdor i conserva el contingut de les
      seccions coincidents.
- [ ] `PATCH` de seccions sense una obligatòria → 422
      `template-required-missing`; sense una opcional → 200.
- [ ] `draft/stream` inclou `<contingut_minim>` al prompt quan la secció té
      `guidance` (comprovat amb proveïdor simulat).
- [ ] Auditoria: cada escriptura deixa la seva entrada.
- [ ] Contract testing contra `openapi.yaml` verd; client TS regenerat; lint
      i tests del frontend verds.
- [ ] Pantalla d'administració i canvis del generador verificats en viu
      (plantilla transcrita d'un plec tipus de la Generalitat → índex amb IA
      que la respecta).
