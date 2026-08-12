# Pantalles d'administració: usuaris i departaments (Estat: implementada)

## Context i objectiu

Les rutes `/admin/users` i `/admin/departments` eren «en construcció»: l'API completa existeix des de la Fase 0 ([users-departments.md](users-departments.md)) però l'única manera de crear usuaris i departaments era Swagger. Aquesta PR és **només frontend** sobre els endpoints existents.

## Comportament

- **/admin/users** (visible amb `users:read`; les escriptures només si `users:write` — admin):
  - Taula: nom, correu, rol (etiqueta en català), departaments, actiu, flags (auditoria/pla). Filtres per rol i actius.
  - **Alta** (formulari en panell): nom, correu, rol, contrasenya (obligatòria per a usuaris locals; validació de política al servidor), departaments (selecció múltiple), flags.
  - **Edició** (clic a la fila): rol, actiu, departaments, flags, restabliment de contrasenya opcional. El correu no s'edita (identitat).
  - Errors del servidor (409 correu duplicat, 422 política de contrasenya) mostrats al formulari, mai silenciats.
- **/admin/departments** (visible amb `departments:write` — admin i resp. contractació):
  - Taula: codi, nom, descripció, actiu. Alta i edició en panell (codi, nom, descripció, actiu). 409 de codi duplicat mostrat al formulari.
- Sense canvis d'URL per estat de panells (transitori); la resta segueix 10-ui (a11y: labels, focus al panell en obrir-lo, botons amb estat de càrrega).

## Canvis d'API

Cap.

## Seguretat i permisos

- Els botons d'escriptura només es mostren amb l'acció corresponent a `GET /me/permissions`; el servidor continua sent l'única autoritat (les denegacions ja estan testades a l'API).

## Fora d'abast

- Vinculació Gestiona del departament (`gestiona_group_id`, Fase 2) i mapatges LDAP.
- Baixa física (l'API només desactiva).

## Criteris d'acceptació

- [x] Alta i edició d'usuari amb departaments i flags; errors 409/422 visibles.
- [x] Alta i edició de departament; 409 visible.
- [x] Botons ocults sense permís d'escriptura.
- [x] tsc/eslint/vitest verds.
