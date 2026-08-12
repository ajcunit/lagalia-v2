# Marc de connectors i connector Socrata (Estat: implementada)

## Context i objectiu

Segona PR de la Fase 1: el hub d'integracions de [08-hub-integracions.md](../docs/08-hub-integracions.md) §1 (plugins amb manifest, credencials xifrades, activables) i el connector `socrata` §2.1 — el client de lectura de Transparència Catalunya amb query builder SoQL segur. Els jobs de sync que el consumeixen arriben a la PR següent.

## Comportament

Donat el connector `socrata` registrat i activat,
Quan un job demana la capacitat de lectura al hub,
Aleshores rep un client configurat (datasets, credencials desxifrades) que consulta l'API amb consultes construïdes pel query builder — mai per concatenació.

Regles verificables:

- **Taules** (migració 0005, [04-model-de-dades.md](../docs/04-model-de-dades.md) §8): `connectors` (`slug UNIQUE`, `enabled`, `mode native|n8n_bridge`, `manifest JSONB`, `config JSONB`, `health_status`, `last_health_check`) i `connector_credentials` (`value_encrypted BYTEA` amb el xifrat AES-256-GCM de `core/crypto`, `rotated_at`).
- **Hub** (`app/integrations/hub.py`): registre de connectors natius per slug; `get_connector(session, slug)`:
  - registra la fila si no existeix (a partir del manifest, **desactivat per defecte**);
  - connector desactivat → `409` Problem `connector-disabled` (mai errors críptics);
  - injecta la configuració (defaults del manifest ⊕ `config` de la fila) i les credencials **desxifrades pel hub** — cap connector llegeix secrets pel seu compte.
- **Query builder SoQL** (`app/integrations/socrata/query.py`), corregeix les injeccions v1:
  - noms de camp i de dataset validats per patró estricte; valors de text escapats (dobla `'`) i sempre dins de literals;
  - validadors tipats: `codi_ine10` `^\d{10}$`, dates ISO (`date/datetime.fromisoformat`), imports numèrics (`Decimal`);
  - construeix `$select/$where/$order/$limit/$offset`; cap mètode accepta SoQL cru.
- **Client** (`socrata/client.py`): httpx async; paginació per `$offset` fins a pàgina curta; **reintents amb backoff exponencial (3 intents)** sobre 5xx i errors de connexió (mai sobre 4xx); throttling per interval mínim entre peticions (token bucket simple); `X-App-Token` opcional via credencial `app_token`; timeouts explícits.
- **Manifest socrata**: datasets configurables amb defaults `ybgg-dgi6` (majors), `hb6v-jcbf` (RPC: pròrrogues/modificacions/menors), `wxdw-5eyv` (CPV); `base_url` configurable.
- **Healthcheck**: consulta d'1 fila al dataset de contractes; actualitza `health_status`/`last_health_check`.
- **Tests sense xarxa**: el client es prova amb `httpx.MockTransport` i respostes gravades; el builder amb casos d'injecció reals.

## Canvis d'API

Cap: la gestió de connectors per API/UI (`connectors:manage`) arriba a la Fase 2. El hub és intern.

## Canvis de dades

Migració `0005_connectors`: `connectors` + `connector_credentials` + enum `connector_mode` + triggers. Reversible.

## Seguretat i permisos

- Credencials write-only a la BD (xifrades); mai a logs ni a manifests.
- `verify=False` no existeix enlloc (lint de CI); CA bundle del sistema.
- El builder no exposa cap via de SoQL cru; les URLs de dataset es validen (`^[a-z0-9]{4}-[a-z0-9]{4}$`).
- Rate limiting propi per no castigar l'API pública.

## UI

Cap (pàgina d'admin de connectors: Fase 2).

## Fora d'abast

- Jobs de sync i mapeig A1 (PR F1-3/4).
- Mode `n8n_bridge` executable (el camp existeix; la passarel·la arriba amb `gestiona`, Fase 2).
- Endpoints d'administració de connectors i healthcheck programat.
- Connector `pscp` (PR F1-7).

## Criteris d'acceptació

- [x] El builder rebutja camps invàlids, INE10 mal format, dates no ISO; un valor amb `' OR 1=1` queda escapat dins del literal.
- [x] El client pagina fins a pàgina curta i reintenta amb backoff sobre 503 (verificat amb MockTransport).
- [x] `get_connector` sobre connector desactivat → Problem 409; activat → client funcional amb credencials desxifrades.
- [x] Migració 0005 reversible; `ruff`, `mypy --strict` i tota la suite verds.
