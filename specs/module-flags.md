# Mòduls activables des de la configuració (Estat: implementada)

## Context i objectiu

Petició de l'Esteve (2026-08-18): tots els mòduls han de ser activables o
desactivables des de la configuració, sense desplegar ni tocar la BD a mà.

## Comportament

- Registre únic a `app/core/modules.py`: clau → etiqueta. Mòduls:
  `minor_contracts`, `contractors`, `tasks`, `favorites`, `cpv`,
  `super_search`, `docgen`, `analyst`, `chat`, `risk_audit`, `compliance`,
  `plan`, `webhooks`.
- **El nucli no és desactivable mai**: contractes, usuaris/departaments,
  configuració, sincronitzacions, jobs i auditoria de seguretat.
- Estat persistit al setting `modules.disabled` (llista JSON). El `PUT`
  del setting **valida contra el registre** (claus desconegudes o del
  nucli s'ignoren) i invalida la cache.
- **Aplicació en un sol punt**: middleware de l'API que mapeja prefixos de
  ruta → mòdul (p. ex. `/chat` → chat, `/ai/analyses` → analyst,
  `/audit/…` → risk_audit — `/audit-log` és nucli i no hi casa) i respon
  `403 module-disabled` per als desactivats. Cache de 15 s per procés;
  el PUT la invalida a l'instant al procés de l'API.
- `GET /me/permissions` retorna `disabled_modules`: el menú i les targetes
  del hub d'administració amaguen les entrades dels mòduls desactivats
  (webhooks i duplicats d'adjudicataris inclosos).
- **Pantalla**: pestanya **Mòduls** a /admin/config (Paràmetres · Mòduls ·
  Connectors · LDAP) amb un commutador per mòdul (`config:write`). Les
  dades no s'esborren mai: desactivar només talla l'accés.

## Canvis d'API

`GET /me/permissions` + `disabled_modules` (openapi + client TS). Cap
endpoint nou: l'estat viu al setting `modules.disabled`.

## Seguretat

- La desactivació NO substitueix permisos: la matriu A2 s'aplica igual.
- El tall és al servidor (middleware), no només al menú.
- Jobs interns (sincros, RAG) no passen pel middleware: desactivar un
  mòdul no atura la ingesta de dades, només l'accés d'usuaris.

## Fora d'abast

- Missatge dedicat al frontend quan es navega directament a una ruta
  desactivada (avui: error de càrrega genèric del 403).

## Criteris d'acceptació

- [x] Desactivar un mòdul talla la seva API (403) i l'amaga del menú.
- [x] Reactivar-lo ho restaura tot sense pèrdua de dades.
- [x] El nucli no es pot desactivar ni per API.
- [x] Bateries verdes.
