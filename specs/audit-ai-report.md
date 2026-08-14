# Agent auditor: informe executiu sobre els red flags (Estat: implementada)

## Context i objectiu

07 §2.2 i A3 (prompt `audit`): els red flags es calculen amb SQL (specs/risk-audit.md) — la IA no inventa numeros; l'agent rep els resultats i redacta l'informe executiu en catala (Markdown), amb prompt addicional opcional de l'interventor.

## Comportament

- `POST /ai/audit/report` `{custom_prompt?}` (accio `audit:run`; sincron interactiu com el classificador): calcula els quatre blocs de red flags (top 5 per bloc, com mana A3) + totals, els serialitza com a dades adjuntes i crida la tasca `audit.report` (resoluble per perfil/model a /admin/ai). Retorna `{report_markdown, generated_at, model}`. Registrat a ai_runs; el resultat NO s'escriu enlloc (suport a la revisio, human-in-the-loop).
- Guardrail: el prompt marca les dades com a delimitades i mana no inventar xifres fora de les adjuntes.

### Pantalla (seccio a /audit)

- «Informe executiu amb IA»: camp opcional d'instruccions de l'interventor + boto generar; el Markdown es mostra a la mateixa pantalla amb boto de copia. Nota visible: es un suport, no substitueix l'informe d'Intervencio.

## Fora d'abast

- Informes periodics programables (job mensual → PDF + email, 07 §2.2); preguntes ad-hoc de l'analista; desar informes.

## Criteris d'acceptacio

- [x] Informe amb dades reals; custom_prompt inclos; sense permis → 403.
- [x] Tasca `audit.report` configurable per perfil/model.
- [x] Seccio a /audit; bateries verdes.
