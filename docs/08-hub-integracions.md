# 08 — Hub d'integracions

Tota comunicació amb sistemes externs passa per **connectors** registrats al hub: **plugins activables i desactivables** amb interfície comuna, credencials xifrades, salut monitorada i execució via jobs. Cap crida externa dins d'una request HTTP d'usuari (excepte proxies de lectura amb whitelist).

## 1. Model de plugin

Cada connector és un plugin amb **manifest** declaratiu i un dels dos **modes d'execució**:

```yaml
# manifest del connector (exemple)
slug: gestiona
name: Gestiona (esPublico)
version: 1.2.0
mode: native          # native | n8n_bridge
capabilities: [user_auth, group_lookup, file_create]
config_schema:        # JSON Schema → formulari d'admin autogenerat
  pool_url: {type: string, format: uri}
credentials: [addon_token]      # gestionades xifrades pel hub
events_consumed: [contract.created]
events_emitted: [gestiona.file_created]
```

```python
class Connector(Protocol):
    manifest: Manifest
    def healthcheck(self) -> HealthStatus            # provat des de la UI i pel monitor
    def capabilities(self) -> list[Capability]        # què ofereix (sync, webhook, lookup...)
    # credencials injectades desxifrades pel hub, mai llegides directament de settings
```

Propietats del sistema de plugins:
- **Activable/desactivable en calent** des de la UI d'admin (equivalent generalitzat dels toggles de mòdul de la v1): desactivar un connector pausa els seus jobs, amaga les seves accions a la UI i fa que els endpoints que en depenen responguin `409 connector_disabled` — mai errors críptics.
- El **domini no coneix els connectors**: consumeix *capacitats* (p. ex. `FileCreator`, `DirectoryLookup`) resoltes pel hub. Si cap plugin actiu ofereix la capacitat, la funcionalitat es degrada de forma controlada.
- Cada connector té: pàgina pròpia a la UI d'admin (activar, formulari generat del `config_schema`, credencials write-only, botó "provar connexió", últimes execucions i errors), scopes API per gestionar-lo (`connectors:manage`) i mètriques (latència, errors, quota consumida).
- Versionat del manifest i migracions de config pròpies del plugin.

### 1.1 Mode `n8n_bridge`: prototipar a n8n, migrar a codi

Requisit explícit del projecte: una integració pot **néixer com a flux n8n i migrar després a codi natiu** sense que la resta del sistema se n'assabenti.

- En mode `n8n_bridge`, el hub no implementa la lògica: **reenvia la invocació de capacitat a un webhook n8n** (signat HMAC, amb timeout i reintents) i valida la resposta contra l'esquema de la capacitat. n8n fa la feina (crides a l'API de tercers, transformacions) i respon amb el contracte pactat.
- **El contracte és de la capacitat, no de la implementació**: `FileCreator.create(payload) → {file_code, external_id}` és idèntic tant si el resol n8n com codi Python. Migrar = escriure el connector natiu, provar-lo amb els mateixos contract tests, i canviar `mode` al manifest — cap canvi al domini, a la UI ni a l'API.
- Les invocacions bridge queden registrades igual que les natives (`webhook_deliveries`/`job` amb payload i resposta) → quan es migra, hi ha un corpus real de casos per als tests.
- Guardrails del bridge: URL n8n validada (https, anti-SSRF), secrets mai al payload (n8n té les seves pròpies credencials del tercer), esquema de resposta estricte, circuit breaker si n8n no respon.
- **Exemple real v1**: la creació d'expedients a Gestiona ja funciona així (webhook n8n). A la v2 això és simplement el connector `gestiona` amb `file_create` en mode `n8n_bridge`, migrable a natiu quan el contracte estigui madur.

## 2. Connectors de la v2 (paritat + millores)

### 2.1 `socrata` — Transparència Catalunya (font primària)
- Datasets: contractes majors (`ybgg-dgi6`), Registre Públic de Contractes — pròrrogues/modificacions/menors (`hb6v-jcbf`), diccionari CPV (`wxdw-5eyv`). URLs configurables per dataset.
- **Query builder SoQL parametritzat** (corregeix les injeccions v1): validació de `codi_ine10` (`^\d{10}$`), dates ISO, imports numèrics.
- Paginació per `$offset` amb límit configurable; **sincronització incremental** per `data_actualitzacio` quan el dataset ho permet (optimització prevista al PRD original i mai feta).
- Conserva com a especificació el mapeig camp-a-camp v1 (documentat a [02-especificacio-funcional.md](02-especificacio-funcional.md) §3.9) i la lògica de fusió menors+liquidacions.
- Rate limiting propi (token bucket) i reintents amb backoff (3 intents).

### 2.2 `pscp` — contractaciopublica.cat (enriquiment i documents)
- Descàrrega dels JSON de fase (`phase_urls`) i de documents (`/portal-api/descarrega-document/{id}/{hash}`).
- Extracció d'escalars/criteris/mesa/documents segons l'esquema v1 (multiidioma ca→es→en).
- Throttling respectuós configurable (v1: 2 s/petició, lots de 5 amb pausa de 5 s) — ara asíncron real, sense bloquejar workers.
- Els documents descarregats es persisteixen a object storage i s'encuen per a indexació RAG.

### 2.3 `gestiona` — esPublico Gestiona
Dues potes, com a la v1 però endurides:
1. **Pool API** (directa): autorització d'usuari en 3 passos (crear autorització → recollir `access_token` → resoldre `user_id` per DNI), cerca de grups (`/files/assignees/groups`) per al mapeig departament↔grup. TLS verificat (CA bundle configurable), capçaleres `X-Gestiona-Addon-Token` / `X-Gestiona-Access-Token`, tokens per usuari xifrats a `user_credentials`.
2. **Creació d'expedients via n8n**: `POST` signat al webhook n8n amb el payload de contracte (codi, objecte, tipus, adjudicatari, imports, departaments amb els seus grups Gestiona, responsables); processa la resposta (`codi_expedient` definitiu + `id_gestiona`) i renombra l'expedient local amb historial `gestiona_webhook`. 🔁 El token personal de Gestiona **no s'inclou al cos** (debilitat v1): n8n s'autentica a Gestiona amb credencial pròpia, o el hub emet un token efímer d'abast mínim.
- Configuració JSON d'endpoints extensible (com `gestiona_endpoints_config` v1) per adaptar-se a canvis de l'API sense desplegar.

Abast funcional de la integració (a més de la creació d'expedients):
- **Obrir expedient** a Gestiona des de la fitxa del contracte (acció existent a la UI, 02 §expedient).
- **Importar i exportar documents** de l'expedient i **dades del contracte** entre LAGALia i Gestiona (bidireccional, sempre via jobs i amb rastre a `audit_log`).
- **Sincronitzar expedients de factura** vinculats al contracte.
- **Assignació automàtica dels expedients a LAGALia en funció de la unitat gestora de Gestiona**: mapeig configurable **departament LAGALia ↔ unitat gestora de Gestiona** (pantalla de configuració, com el mapeig departament↔grup existent).

### 2.4 `ldap` — Active Directory
- Autenticació bind + cerca `sAMAccountName`, provisió automàtica, mapeig grup→rol/departament (ara a taula `ldap_group_mappings`).
- 🔁 Millores: LDAPS/StartTLS obligatori per defecte, timeout i circuit breaker (si l'AD cau, el login local continua), sincronització opcional programada d'altes/baixes (desactivar usuaris que ja no són al grup).

### 2.5 `smtp` — correu (nou; v1 era un mock)
- Notificacions: alertes de venciment (transició d'alerta), **recordatoris de tasques calendaritzades** (avisos previs configurables + re-avís de vençudes), duplicats pendents als responsables, resum de sincronització fallida a admins, informes d'auditoria programats.
- Plantilles amb capçalera municipal; agrupació diària (digest) configurable per usuari.

### 2.6 `boe` — Boletín Oficial del Estado (nou)
Alimenta el corpus normatiu de l'assistent legal ([07-agents-ia.md](07-agents-ia.md) §2.4 i §3bis) via l'**API de dades obertes del BOE** (`boe.es/datosabiertos`):
- **Legislació consolidada**: descàrrega del text consolidat (XML) de les normes subscrites per identificador BOE (p. ex. LCSP = `BOE-A-2017-12902`), amb parsing per articles i control de versió de consolidació.
- **Vigilància de canvis**: job diari que consulta els sumaris del BOE i l'estat de consolidació de les normes subscrites; si una norma subscrita es modifica → re-descàrrega, re-indexació RAG i esdeveniment `legal.norm_updated` (avís a admins i marca de revisió a les regles del verificador).
- **Alerta temàtica** opcional: cerca als sumaris diaris per matèria "contractació del sector públic" per avisar de normativa nova rellevant (només notificació, mai subscripció automàtica).
- Gestió des de la UI del connector: llista de normes subscrites (afegir per ID BOE), versió indexada, data de l'última comprovació.
- Extensible al **DOGC/Portal Jurídic de Catalunya** per a normativa autonòmica com a segon connector del mateix patró.

### 2.7 `webhooks` — sortints genèrics (nou)
- Subscripcions a esdeveniments de domini ([05-api.md](05-api.md) §4): URL + secret + llista d'esdeveniments.
- Entrega: signatura HMAC SHA-256 (`X-Signature`, `X-Timestamp` anti-replay), reintents exponencials (5 intents), dead-letter visible a la UI amb re-enviament manual.
- Validació anti-SSRF de la URL (https, resolució no privada).
- **n8n com a primer consumidor**: qualsevol automatització municipal (Telegram, Teams, registre d'entrada...) es construeix sobre webhooks + API keys, sense tocar el nucli.

## 3. Jobs de sincronització

| Job | Origen | Programació |
|---|---|---|
| `sync.nightly` | intern | cadena diària configurable (hora, dies, TZ Europe/Madrid; specs/sync-schedule.md): contracts → extensions → menors → execució |
| `sync.contracts` | socrata majors | dins de `sync.nightly` + manual |
| `sync.extensions` | socrata RPC | encadenat després de contracts (dins de `sync.nightly`) + manual |
| `sync.minor_contracts` | socrata RPC (procediment Menor) | dins de `sync.nightly` + manual |
| `sync.execution` | socrata execució (8idu-wkjv) | dins de `sync.nightly` + manual (specs/execution-sync.md) |
| `sync.cpv` | socrata CPV | manual / trimestral |
| `enrich.contract` / `enrich.batch` | pscp | auto per a nous + batch manual (`force`) |
| `rag.index_document` | intern | subscrit a descàrregues |
| `alerts.recompute` | intern | diari + després de cada sync (una sola passada, corregeix l'O(n²) v1) |
| `tasks.reminders` | intern | diari: recordatoris pendents, re-avís de vençudes, emissió de `task.*` |
| `sync.boe_norms` | boe | diari: vigilància de consolidació + re-indexació si hi ha canvis |
| `reports.audit_monthly` | intern | opcional |

Propietats comunes: idempotents (clau de dedup — mai dues syncs simultànies del mateix tipus), progrés observable (`/jobs/{id}` + SSE), cancel·lables, amb `sync_runs`/`job` com a registre. El scheduler usa advisory locks de PostgreSQL (una sola execució encara que hi hagi rèpliques).

## 4. Pipeline d'una sincronització de contractes (referència)

1. Job adquireix lock; crea `sync_run` (`running`).
2. Connector socrata descarrega per pàgines (incremental si és possible).
3. Per registre: normalització (mapeig + àlies d'adjudicatari + parsing de durada/dates) → hash → upsert per (file_code, status, lot).
4. Nous: herència de departaments del mateix expedient → regles d'associació → detecció de duplicats (**sempre**, a diferència de la v1 que divergia segons la via) → encua `enrich.contract`.
5. Fi de pàgina: commit per lots; progrés a Redis.
6. Postprocés: sync de pròrrogues/modificacions (propagació de dates de fi), `alerts.recompute`, detecció de duplicats d'adjudicatari per NIF.
7. Tanca `sync_run` amb comptadors i emet `sync.completed` (→ webhooks, email si `failed`).

## 5. Afegir un connector nou (guia)

**Via ràpida (prototip n8n):**
1. Definir la capacitat i el seu contracte (esquema de petició/resposta) al hub.
2. Crear el manifest amb `mode: n8n_bridge` + URL del flux n8n + secret.
3. Construir el flux a n8n; activar el plugin i provar-lo des de la UI.

**Via nativa (o migració des del bridge):**
1. Crear `integrations/<slug>/` implementant `Connector` + jobs propis.
2. Passar els **mateixos contract tests** de la capacitat (i, si es migra, reproduir els casos reals registrats pel bridge).
3. Canviar `mode: native` al manifest — credencials, formulari d'admin i mètriques ja hi són.

Sense tocar el nucli en cap dels dos casos: el domini només veu capacitats, esdeveniments i dades normalitzades.
