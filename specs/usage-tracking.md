# Seguiment d'ús de la plataforma (Estat: implementada)

## Context i objectiu

B-010 (petició d'usuari, 2026-08-12): seguiment operatiu de què passa a la plataforma — sessions actives, ús de l'API per identitat i endpoint, ràtios d'error. Va lligada a [system-status.md](system-status.md) (B-022) i comparteix pantalla i permís.

## Comportament

Donat un administrador,
Quan obre Configuració → Estat del sistema,
Aleshores veu, a més de la salut, l'ús de la plataforma: sessions actives, peticions i errors per dia, endpoints més usats i usuaris més actius.

Regles verificables:

- **Registre**: un middleware compta cada request de `/api/*` a Redis per **plantilla de ruta resolta** (p. ex. `GET /contracts/{id}`), mai el path cru — cardinalitat continguda i cap identificador de recurs als comptadors. Tres hashos per dia UTC: peticions per endpoint, errors (status ≥ 400) per endpoint i peticions per usuari (només l'id). **TTL de 40 dies**: la retenció és automàtica, sense taula ni migració.
- El registre **mai trenca una request**: qualsevol error de Redis s'engoleix i queda al log (`usage_tracking_failed`).
- La identitat surt de la sessió autenticada (`request.state.user_id`, el posa `get_current_session`); les requests anònimes compten a l'endpoint però no a cap usuari.
- **`GET /system/usage?days=`** (`system:read`, 1–40, 7 per defecte): sèrie diària (peticions/errors), top 15 endpoints amb errors, **mòduls més usats** (cada plantilla d'endpoint mapada amb la mateixa taula que el tall de mòduls desactivats, `core/modules.py`), **usuaris** (fins a 50: unió de qui s'ha connectat mai — última connexió amb èxit i la seva IP, de l'`audit_log` — i qui genera peticions al període, ordenat per activitat), i **sessions actives** (refresh tokens no revocats i no caducats) + usuaris diferents amb sessió.
- Decisió de retenció (pregunta oberta del backlog): **agregats efímers a Redis**; la capa de mètriques OpenTelemetry/Prometheus de docs/03 §3 queda al backlog com a evolució per a qui tingui Grafana.

## Canvis d'API

`openapi.yaml`: nou `GET /system/usage` (tag `system`, esquema `SystemUsage`). Client TS regenerat.

## Canvis de dades

Cap: comptadors a Redis amb TTL. Cap dada personal nova — l'id d'usuari ja existeix i el nom es resol en llegir.

## Seguretat i permisos

- Mateixa acció `system:read` (només admin) que l'estat del sistema.
- Als comptadors no hi va mai el path cru (podria portar identificadors), ni user agents, ni IPs, ni cossos de petició.

## UI

A Configuració → Estat del sistema (pestanyes amb icona): pestanya **Ús** amb totals del període, mòduls més usats i endpoints més usats; pestanya **Usuaris** amb sessions actives i la taula de qui s'ha connectat (última connexió, IP, peticions del període).

## Fora d'abast

- Mètriques OpenTelemetry/Prometheus + Grafana (docs/03 §3) — backlog.
- Latència i quota per connector extern (08 §1) — quan es faci la instrumentació del hub.
- Rate limits assolits com a mètrica pròpia (avui es veuen com a errors 429).

## Criteris d'acceptació

- [x] Una request autenticada incrementa el comptador del seu endpoint i del seu usuari; una request amb error incrementa també el d'errors.
- [x] `GET /system/usage` respon a un admin amb sèrie, tops i sessions actives; 403 a qualsevol altre rol.
- [x] Un Redis caigut no afecta les requests dels usuaris.
