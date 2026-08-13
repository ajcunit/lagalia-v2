# Favorits: carpetes personals amb snapshot extern (Estat: implementada)

## Context i objectiu

02 §2.11 (esmenat 2026-08-14): organitzar expedients del SuperBuscador en carpetes personals. **Els externs mai s'insereixen a `contracts`**: es desen com a snapshot JSONB al mateix modul de favorits (guia per a licitacions i, mes endavant, referencia per als agents redactors). Vegeu memoria del projecte i el canvi corresponent a docs/02.

## Comportament

- **Carpetes personals** (nom ≤100, descripcio ≤500, color de la paleta): cada usuari veu i gestiona NOMES les seves. CRUD complet; esborrar una carpeta esborra els seus favorits (snapshot inclos).
- **Afegir favorit** `POST /folders/{id}/favorites` amb `{file_code}`: es consulta el registre public i es desa el snapshot mapejat (totes les files lot/fase) + camps resum (subject, organisme, publicat). Duplicat dins de la mateixa carpeta → 409. Expedient inexistent → 404.
- **Llistar i treure**: `GET /folders` (amb comptador), `GET /folders/{id}/favorites`, `DELETE /folders/{id}/favorites/{favorite_id}`.
- El detall d'un favorit inclou el snapshot sencer: la fitxa externa funciona offline de la font.

### Pantalla /favorites (zona Operativa, entrada «Favorits»)

- Mestre-detall: carpetes a l'esquerra (color, comptador; crear/editar/esborrar amb confirmacio), favorits de la carpeta a la dreta (targetes com les del SuperBuscador, amb fases i enllaç al portal, des del snapshot).
- Des del SuperBuscador: boto «⭐ Desa» a cada targeta amb selector de carpeta (o crear-ne una al vol).

## Canvis d'API

`GET/POST /folders`, `PATCH/DELETE /folders/{id}`, `GET/POST /folders/{id}/favorites`, `DELETE /folders/{id}/favorites/{favorite_id}` (tag `favorites`, accio `tools:use` — es material personal, cap abast departamental).

## Canvis de dades

Migracio 0014: `favorite_folders` (user_id FK CASCADE, name, description, color) i `favorites` (folder_id FK CASCADE, file_code, subject, awarding_body, published_at, snapshot JSONB, UNIQUE(folder_id, file_code)).

## Seguretat

- Propietat estricta: tota operacio filtra per `user_id` de la sessio (404 si la carpeta no es teva, mai 403 que confirmi l'existencia).
- El snapshot es de dades publiques; cap dada personal.

## Fora d'abast

- Compartir carpetes; enviar snapshot al cartipas del generador (2.14); refresc automatic del snapshot.

## Criteris d'acceptacio

- [x] CRUD de carpetes nomes del propietari; usuari B no veu les d'A.
- [x] Afegir per file_code desa snapshot sense tocar `contracts` (comptatge igual abans/despres).
- [x] Duplicat → 409; inexistent → 404.
- [x] Pantalla mestre-detall + desar des del SuperBuscador.
- [x] Bateries verdes.
