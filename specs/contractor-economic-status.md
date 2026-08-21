# Estat econòmic de l'adjudicatari en contractes menors (Estat: implementada)

## Context i objectiu

Petició d'usuari (2026-08-21): dins de la fitxa de l'adjudicatari cal la **suma dels imports dels contractes menors**, i **tothom** l'ha de poder consultar per saber si el proveïdor pot seguir rebent contractes menors (control del límit de l'art. 118 LCSP abans d'adjudicar).

## Comportament

Donat qualsevol usuari amb accés a la fitxa d'un adjudicatari,
Quan obre la pestanya «Menors»,
Aleshores veu les sumes dels contractes menors **per exercici** amb el desglossament **per tipus**, agregades a tot l'ajuntament, amb avisos quan l'exercici en curs s'acosta o supera els llindars de referència.

Regles verificables:

- **`GET /contractors/{id}/minor-totals`** (`contracts:read` — tots els rols en tenen): per exercici (més recent primer): comptador i suma, i desglossament per `contract_type`. Adjudicatari inexistent → 404.
- **Agregat de tot l'ens, deliberadament**: el límit de menors per adjudicatari no entén de departaments — l'abast departamental continua aplicant-se als LLISTATS de menors (allà es veu el detall), però la suma és global perquè si no la comprovació legal no serveix de res. Només s'exposen comptadors i imports agregats, mai el detall dels expedients d'altres departaments.
- **UI**: pestanya **«Menors»** (icona Receipt) a la fitxa de l'adjudicatari, targetes per exercici a tot l'ample. Distintius **només a l'exercici en curs**: «Límit superat» (vermell) i «A prop del límit» (ambre, ≥ 80 %), amb llindars de referència de l'art. 118 LCSP — 15.000 € serveis/subministraments, 40.000 € obres (detecció laxa del tipus: conté «obr» = obres). Nota visible: els distintius són orientatius; la comprovació formal és de l'òrgan de contractació.

## Canvis d'API

`openapi.yaml`: nou `GET /contractors/{id}/minor-totals`. Client TS regenerat.

## Canvis de dades

Cap: agregació sobre `minor_contracts` (`fiscal_year`, `contract_type`, `award_amount`, `contractor_id` ja existeixen).

## Seguretat i permisos

- Mateixa concessió que la fitxa (`contracts:read`): cap rol nou. La decisió d'agregat global (per sobre de l'abast departamental) queda argumentada aquí i al docstring de l'endpoint: és informació necessària per a la legalitat de la contractació i no revela cap detall d'expedient.

## UI

Vegeu Comportament. Els imports amb `formatCurrency` i el format de dates centralitzat.

## Fora d'abast

- Llindars configurables per settings (els de l'art. 118 són estables; si canvien per llei, és un canvi de codi amb spec).
- El mateix desglossament per als contractes majors (el volum global ja surt al resum).
- Bloqueig actiu de l'adjudicació en superar el límit (això és decisió de l'òrgan de contractació, no del sistema).

## Criteris d'acceptació

- [x] Un empleat (rol mínim) consulta les sumes per exercici i tipus de qualsevol adjudicatari.
- [x] Sumes correctes per exercici (més recent primer) i per tipus; 404 per a adjudicatari inexistent.
- [x] Distintius de límit només a l'exercici en curs, amb la nota d'orientativitat.
