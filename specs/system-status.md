# Estat del sistema i observabilitat (Estat: implementada)

## Context i objectiu

B-022: l'administrador no tenia manera de saber des de la mateixa aplicació si el sistema és viu **de veritat**. Un contenidor pot constar com a «running» amb el procés en crash-loop (cas real: l'API amb `httpx` absent es veia igual que una API sana des de Portainer), i el worker o el scheduler no tenen healthcheck de Docker. Aquesta feature dona una pantalla d'administració amb salut per servei provada amb feina real, tasques en execució, consums de recursos i incidències recents.

Completa també un deute de contracte: `GET /health/ready` era a `openapi.yaml` des de la fase 0 sense implementar.

## Comportament

Donat un administrador,
Quan obre Configuració → Estat del sistema,
Aleshores veu l'estat real de cada servei, els treballs en curs i els consums, refrescats periòdicament, i pot distingir «el procés existeix» de «el servei fa la seva feina».

Regles verificables:

- **`GET /health/ready`** (`system:read`): comprovacions **en viu** de la infraestructura interna — `database` (SELECT 1), `redis` (PING), `storage` (HeadBucket o accés al directori local) — amb `status` per check (`ok|degraded|failing`, degraded per latència > 500 ms) i `latency_ms`. L'estat global és el pitjor dels checks. Només infraestructura interna: **cap crida a serveis externs dins de la request** (prohibició de CLAUDE.md).
- **`GET /system/status`** (`system:read`): tot el de dalt més:
  - **worker**: edat de l'últim `system.heartbeat` acabat amb èxit (jobs, cada 5 min). ≤ 15 min `ok`, ≤ 30 min `degraded`, més vell o inexistent `failing`. És la prova que el worker *executa*, no que el procés existeix.
  - **scheduler**: edat de l'últim tick (el scheduler escriu `system:scheduler_tick` a Redis a cada volta). ≤ 60 s `ok`, ≤ 300 s `degraded`, més `failing`.
  - **connectors actius**: `health_status` i `last_health_check` de `connector_records` — els refresca el job de fons, mai la request.
  - **treballs**: en cua, en marxa (llista amb progrés i missatge), morts (DLQ) i fallats les últimes 24 h.
  - **sincronitzacions**: última execució per tipus amb estat.
  - **webhooks**: entregues pendents i fallades les últimes 24 h.
  - **recursos**: mida de la BD (`pg_database_size`), memòria de Redis (INFO), fondària de la cua i ús de l'emmagatzematge d'objectes (del job de fons; amb marca de truncament si hi ha més objectes que el límit mesurat).
- **Job `system.status_snapshot`** (programat cada 15 min): executa el healthcheck de cada connector **habilitat** i actualitza `connector_records`; mesura l'ús de l'storage (fins a 10.000 objectes, després trunca) i el desa al setting `system.storage_usage`. Les crides potencialment lentes o externes viuen aquí, no a la request.
- La resposta no conté mai secrets ni payloads de jobs (només tipus, progrés i missatge).

## Canvis d'API

`openapi.yaml`: `GET /health/ready` passa de contracte a implementat (esquema intacte); nou `GET /system/status` amb `SystemStatus*` (tag `system`, `x-required-scopes: [system:read]`). Client TS regenerat.

## Canvis de dades

Cap migració. Reutilitza `jobs`, `sync_runs`, `webhook_deliveries`, `connector_records` (camps `health_status`/`last_health_check` existents) i un setting nou (`system.storage_usage`). El tick del scheduler viu a Redis.

## Seguretat i permisos

- Acció `system:read`, **només admin** (ja reservada a la matriu A2 i a la taula de veritat; ara s'usa). Cap check de rol al router: `Authorize("system:read")`.
- Les comprovacions en viu són només d'infraestructura interna del compose; els connectors externs es consulten al job de fons amb el mateix camí (`hub.get_connector`) que la resta del sistema.
- Lectura sense auditoria (com la resta de GETs); el job de fons no escriu res sensible.

## UI

Configuració → **Estat del sistema** (`/admin/system`, primera targeta del hub, acció `system:read`): targetes **a tot l'ample i apilades** (mai graella) — Serveis (punt de color + nom + detall + latència/edat), Treballs (comptadors + llista d'execucions amb barra de progrés), Sincronitzacions (última per tipus), Recursos (mides llegibles). Refresc automàtic cada 15 s amb indicador d'última actualització.

## Fora d'abast

- CPU/memòria dels contenidors: caldria muntar el socket de Docker dins del contenidor (porta d'escalada, mai) o un agent extern (cAdvisor/Prometheus) — si es vol, backlog nou.
- Alertes push/correu quan un servei cau (B-022 només observació; l'avís actiu seria una extensió).
- Històric i gràfiques d'evolució (només l'estat actual i les últimes 24 h).

## Criteris d'acceptació

- [x] `GET /health/ready` i `GET /system/status` responen a un admin i denegen (403) qualsevol altre rol.
- [x] El check del worker surt `failing` sense cap heartbeat i `ok` amb un heartbeat recent.
- [x] El job `system.status_snapshot` actualitza `connector_records` i el setting d'ús de l'storage sense tombar-se si un connector falla.
- [x] La pantalla mostra serveis, treballs, sincronitzacions i recursos apilats a tot l'ample, amb refresc automàtic.
</content>
