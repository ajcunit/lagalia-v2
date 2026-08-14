# Cercador CPV (Estat: implementada)

## Context i objectiu

02 §2.9: cerca manual per codi o descripcio i arbre navegable amb lazy-load. Ruta `/cpv` (zona Intel·ligencia, accio `tools:use`). El diccionari (9.455 codis, `cpv_codes`) ja s'ingesta amb `sync.cpv`.

## Comportament

`GET /cpv` (params exclusius combinables segons el mode):
- `query` (≥2 chars): prefix de codi (si comença per digit) o subcadena de descripcio (ILIKE sobre l'index trigram), maxim 50, ordenat per codi.
- `parent`: fills directes d'un codi (arbre lazy); `parent=` absent i sense query → arrels (Division).
- `level` opcional per filtrar.
- Cada resultat: code, description, level, parent_code, `has_children` (per pintar l'expansor sense una segona crida).

### Pantalla /cpv

- Caixa de cerca (debounce 300 ms) amb resultats en taula; en netejar, torna l'arbre.
- Arbre per nivells amb expansio lazy (Division → Group → Class → Category), sagnat i badge de nivell.
- Boto «copia» del codi a cada fila.

## Fora d'abast

- Suggeriments amb IA (02 §2.9, pipeline hibrid) — arriba amb la plataforma d'IA.

## Canvis d'API

`GET /cpv` (tag `reference`). Cap canvi de dades.

## Criteris d'acceptacio

- [x] Cerca per text i per prefix de codi; arrels i fills; has_children correcte.
- [x] Pantalla amb cerca i arbre lazy.
- [x] Bateries verdes.
