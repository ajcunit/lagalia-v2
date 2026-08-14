# Pla anual de contractacio (Estat: implementada)

## Context i objectiu

02 §2.13 i 04 §6. Planificacio d'expedients per exercici i trimestre amb workflow d'aprovacio. Ruta `/plan` (zona Intel·ligencia), accions A2 existents: `plan:read` (tots els rols amb flag `can_plan`; admins sempre), `plan:write` (crea/edita; els no-admins creen en estat `pending`), `plan:approve` (nomes admin).

## Comportament

- `GET /plan?fiscal_year=` — entrades de l'exercici (selector −1..+3), ordenades per trimestre; inclou el nom del departament i, si escau, el contracte vinculat.
- `POST /plan` — subject, quarter 1–4, fiscal_year, contract_type?, scope?, notes?, subsidized, estimated_amount?, department_id?, contract_id? (vincle opcional a expedient real). Estat inicial: `approved` si admin, `pending` altrament.
- `PATCH /plan/{id}` — edicio; si un no-admin edita una entrada aprovada, torna a `pending`.
- `POST /plan/{id}/actions/approve` — nomes `plan:approve`.
- `DELETE /plan/{id}` — autor o admin.
- `GET /plan/expiring?fiscal_year=` — contractes reals que caduquen dins l'exercici, agrupats per trimestre de `calculated_end_date` (exclou obres — `contract_type ILIKE '%obres%'` fora — i anul·lats), per detectar renovacions a planificar.
- Tota escriptura s'audita (`plan.*`).

### Pantalla /plan

- Selector d'exercici (−1..+3); entrades agrupades per trimestre amb badge d'estat (pendent/aprovada), alta i edicio inline, aprovacio (admins) i esborrat amb confirmacio.
- Seccio «contractes que caduquen» per trimestre amb enllaç a la fitxa.

## Canvis de dades

Migracio 0015: `plan_entries` segons 04 §6 + `created_by` FK users, timestamps.

## Fora d'abast

- Notificacions d'aprovacio; export; vincle invers des de la fitxa del contracte.

## Criteris d'acceptacio

- [x] No-admin crea en `pending`; admin aprova; editar una aprovada la retorna a `pending`.
- [x] Caduquen per trimestre sense obres ni anul·lats.
- [x] Pantalla completa; bateries verdes.
