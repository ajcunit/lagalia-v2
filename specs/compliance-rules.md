# Assistent legal — capa 1: motor de regles determinista (Estat: implementada)

## Context i objectiu

07 §2.4.1 i roadmap F3 (avançable, no depen de cap LLM): llindars i limits de la LCSP codificats com a regles versionades i datades, cada una amb l'article de referencia. La capa 2 (revisio LLM amb RAG normatiu) arriba amb el RAG.

## Comportament

### Motor (`app/modules/compliance/engine.py`)

- **Regles versionades en codi** (registre amb: id, article LCSP, `effective_from`/`effective_to`, parametres): els subjectes es validen amb la norma vigent a la seva data (menors: award_date/fiscal_year; pla: exercici).
- Regles inicials (art. 118 LCSP i concordants):
  - `minor.amount`: menor de serveis/subministraments > 15.000 € (obres > 40.000 €) sense IVA.
  - `minor.duration`: menor amb durada > 1 any (mai prorrogable).
  - `contract.minor_procedure_amount`: contracte amb procediment «menor» i import sobre el llindar del seu tipus.
  - `plan.minor_over_threshold`: entrada del pla amb tipus menor/import estimat sobre llindar → avis en fase de planificacio (exemple del roadmap).
- Resultat per comprovacio: `conforme | avis | no_conforme | no_verificable` + justificacio + article.

### API (accio `compliance:run`; tag `compliance`)

- `GET /compliance/rules` — registre de regles amb article, vigencia i parametres (transparencia).
- `POST /compliance/check` `{subject_type: contract|minor_contract|plan_entry, subject_id}` — executa i **persisteix** a `compliance_reviews` (migracio 0020, 04 §7: subject, status = pitjor semafor, findings JSONB, created_by; `ai_run_id` NULL fins la capa 2).
- `POST /compliance/check-plan` `{fiscal_year}` — batch sobre les entrades del pla de l'exercici; retorna findings per entrada (i persisteix una review per entrada amb avisos).

### Pantalla

- A **/plan**: boto «Revisio legal del pla» → taula de resultats amb semafor per entrada (conforme/avis/no conforme), justificacio i article. Nota visible: suport, no substitueix l'informe juridic.

## Fora d'abast

- Capa 2 LLM+RAG normatiu i connector boe; revisio de documents/plecs; boto a la fitxa del contracte (seguent tanda amb B-012); mes regles (garanties, modificacions art. 203-207, terminis de publicitat) — s'afegiran al registre.

## Criteris d'acceptacio

- [x] Llindars per tipus i data d'efecte; menors reals i entrades del pla validats.
- [x] Reviews persistides amb rastre; sense permis → 403.
- [x] Boto al pla amb semafor; bateries verdes.
