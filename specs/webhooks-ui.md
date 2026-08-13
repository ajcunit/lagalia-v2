# Pantalla d'administració de webhooks (Estat: implementada)

## Context i objectiu

UI d'administració dels webhooks sortints ([outbound-webhooks.md](outbound-webhooks.md)). Només frontend.

## Comportament

- **/admin/webhooks** (entrada nova a administració, `webhooks:manage` — admin):
  - Taula: nom, URL, esdeveniments subscrits (xips), estat actiu/inactiu, data.
  - **Alta**: nom, URL (https; http acceptat pel servidor només en desenvolupament) i selector d'esdeveniments (catàleg amb etiquetes en català + opció «Tots (*)»).
  - **En crear, el secret es mostra UNA sola vegada** en un quadre destacat amb botó de copiar i l'avís que no es tornarà a veure (així es configura la verificació HMAC a n8n).
  - Accions per fila: **Prova** (encua `webhook.test` i recorda revisar el receptor), **Activa/Desactiva**, **Elimina** (amb confirmació), i **Enviaments** — desplegable amb l'històric de deliveries (estat, intents, últim error, pròxim reintent).
  - Errors del servidor visibles al formulari (URL no https, etc.).

## Fora d'abast

- UI de service accounts (arribarà amb el seu backend).
- Regeneració del secret (avui: eliminar i recrear; anotat com a millora).

## Criteris d'acceptació

- [x] Alta amb secret visible només un cop i copiable; llista amb events i estat.
- [x] Prova, activació/desactivació i eliminació amb confirmació; deliveries consultables.
- [x] tsc/eslint/vitest verds.
