# Pantalles d'adjudicataris (Estat: implementada)

## Context i objectiu

Rànquing, fitxa i revisió de duplicats d'adjudicataris ([02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) §2.6) sobre l'API existent ([minor-contractors-api.md](minor-contractors-api.md)). Només frontend.

## Comportament

- **/contractors** (amb `contracts:read`, entrada nova a la navegació): rànquing unificat (majors + menors) amb cerca per nom/àlies/NIF i ordenació per volum total, nombre de contractes o nom; columnes: nom, NIF, contractes (majors i menors) i imports. Paginació per cursor.
- **/contractors/{id}**: fitxa amb dades de l'empresa (nacionalitat, tipus, tercer sector, contacte), àlies coneguts i **contractes vinculats** (enllacen al llistat de majors filtrat per adjudicatari i al de la fitxa de cada contracte).
- **/contractors/duplicates** (amb `duplicates:manage` — admin i resp. contractació; entrada a la zona d'administració): parells pendents amb els dos candidats costat a costat (nom, NIF, volum), accions **Fusiona a l'1 / Fusiona al 2 / Rebutja** amb confirmació i notes opcionals; pestanya per veure els resolts. 409 (ja resolt) visible.
- > ⚠️ La revisió **agrupada per NIF** (B-011) queda pendent del backend; mentrestant la pantalla treballa amb parells i mostra l'avís del volum pendent.

## Canvis d'API

Cap.

## Criteris d'acceptació

- [x] Rànquing cercable i ordenable; fitxa amb àlies i enllaços.
- [x] Resolució de duplicats amb confirmació; errors visibles; llista de resolts.
- [x] Entrades de navegació noves amb els permisos correctes.
- [x] tsc/eslint/vitest verds.
