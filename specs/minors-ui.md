# Pantalles de contractes menors (Estat: implementada)

## Context i objectiu

Llistat i fitxa dels contractes menors ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.5) sobre l'API existent ([minor-contractors-api.md](minor-contractors-api.md)). Només frontend.

## Comportament

- **/minor-contracts** (visible amb `minor_contracts:read`, entrada nova a la navegació):
  - Llistat amb estat a la URL (com el de majors): cerca amb debounce, filtres exercici / amb o sense liquidació / sense departament / departament, ordenació per data d'adjudicació, import i expedient; paginació per cursor; commutador «els meus / tots» per a qui té Vista Admin.
  - Columnes: expedient, descripció, adjudicatari, import, data d'adjudicació, exercici i badge de liquidació.
- **/minor-contracts/{id}**: seccions expedient (tipus, descripció, estat intern), imports i liquidació (tipus, data, import), durada (anys/mesos/dies) i departaments.
  - **Edició** (amb `minor_contracts:update` — admin i resp. contractació): estat intern i departaments, amb desada via PATCH i errors visibles.
- Fora d'abast → 404 (pantalla «no trobat», com a majors).

## Canvis d'API

Cap. (L'assignació massiva de menors queda per a quan s'afegeixi l'endpoint `bulk/assign-departments` de menors; anotat.)

## Fora d'abast

- Exportació CSV de menors (reutilitzarà el job genèric).
- Assignació massiva (sense endpoint encara).

## Criteris d'acceptació

- [x] Llistat filtrable i ordenable amb URL com a estat; fitxa completa amb liquidació.
- [x] Edició d'estat intern i departaments només per a rols amb permís; errors del servidor visibles.
- [x] tsc/eslint/vitest verds.
