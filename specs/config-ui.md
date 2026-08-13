# Configuracio: parametres i connectors, amb pantalla (Estat: implementada)

> Ampliacio 2026-08-13: `POST /connectors/smtp/actions/send-test-email` (config:write)
> envia un correu de prova a l'admin autenticat i retorna `sent|failed` amb detall;
> mai tomba l'API i s'audita (`config.smtp_test_email`). Boto «Envia'm un correu de
> prova» a la targeta smtp. Diagnostic sincron explicit d'admin, com el healthcheck
> (excepcio deliberada a la regla de cua per a crides externes: el resultat immediat
> es el valor del boto).

## Context i objectiu

Fins ara els connectors (socrata, pscp, smtp) i els parametres nomes es podien tocar per BD. API + pantalla de configuracio (02 §2.13; 08 §1).

## Comportament

- **API** (`config:read` lectura per a tothom; `config:write` nomes admin):
  - `GET /settings` — els valors `is_secret` mai es retornen (`is_set`); `PUT /settings/{key}` upsert amb auditoria.
  - `GET /connectors` — manifest + estat (enabled, config amb defaults, credencials com a `nom -> is_set`, salut); `PATCH /connectors/{slug}` (activar/desactivar, config validada contra el manifest); `PUT /connectors/{slug}/credentials` (**nomes escriptura**, xifrades pel hub); `POST /connectors/{slug}/actions/healthcheck` (mai tomba l'API; persisteix l'estat).
- **Pantalla /admin/config**: targeta per connector (commutador actiu, formulari de config generat de les claus del manifest, credencials write-only amb estat «configurada», boto *Comprova la connexio* amb resultat) i taula de parametres editable (secrets emmascarats).
- Corregeix la referencia de task-reminders.md a una «API de connectors existent» que no existia.

## Criteris d'acceptacio

- [x] Activar smtp + posar host/credencials + healthcheck des de la pantalla.
- [x] Secrets i credencials mai en respostes; auditoria per canvi.
- [x] Bateries verdes.
