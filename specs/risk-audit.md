# Auditoria de contractacio: red flags (Estat: implementada)

## Context i objectiu

02 §2.12: deteccio de patrons de risc sobre les dades reals. Ruta `/audit` (zona Intel·ligencia), accio `audit:run` (admins; resta de rols amb flag `can_audit`).

## Comportament

`GET /audit/red-flags` calcula en la request (nomes lectura, BD local, sense crides externes):

1. **Possibles fraccionaments**: adjudicataris (consolidats) amb suma ≥15.000 € en menors els darrers 365 dies (per `award_date`). ⚠️ DESVIACIÓ de la regla v1 («≥2 contractes i suma»): el dataset de menors de l'ens és **una fila agregada per adjudicatari i any** (liquidacions), de manera que el comptador de files no mesura contractes individuals; el senyal útil és la suma anual. Si mai s'ingesta el detall per contracte, restaurar el criteri doble.
2. **Baixes temeraries**: contractes amb `award_amount ≤ 80% · budget_no_vat` (ambdos > 0), amb % de baixa.
3. **Renovacions critiques**: contractes amb `calculated_end_date` entre avui i +6 mesos i estat no finalitzat (`internal_status != finished`).
4. **Falta de concurrencia** (nova v2, endpoint buit a la v1): contractes amb `received_offers = 1` i procediment competitiu (exclou menors i negociats sense publicitat).

Cada bloc va limitat (top 50 per severitat: suma, % de baixa, proximitat, import) amb `total` per bloc. L'execucio s'audita (`audit.red_flags_run`).

### Pantalla /audit

- Quatre seccions amb comptador total, taula ordenada per severitat i enllaç a la fitxa del contracte o de l'adjudicatari.
- Nomes visible amb `audit:run` (entrada de menu «Auditoria» a Intel·ligencia).

## Fora d'abast

- Assistent d'auditoria amb IA (02 §2.12; arriba amb la plataforma d'IA); parametres configurables dels llindars (backlog si es demana); export.

## Canvis d'API

`GET /audit/red-flags` (tag `audit`). Cap canvi de dades.

## Criteris d'acceptacio

- [x] Quatre deteccions amb llindars de la spec; sense permis → 403.
- [x] Pantalla amb les quatre seccions.
- [x] Bateries verdes.
