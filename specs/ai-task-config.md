# Configuracio de proveidor i model per tasca d'IA (Estat: implementada)

## Context i objectiu

07 §1.1/§4: cada tasca d'agent referencia un perfil+model+parametres. Fins ara els agents agafaven el primer perfil actiu; aixo ho fa configurable des de /admin/ai. Motivacio immediata: poder separar `cpv.extract` (massiva, model economic) de `cpv.rank` (qualitat) i sobreviure a retirades de models (cas gemini-2.5).

## Comportament

- Migracio 0019: `ai_task_configs` — `task UNIQUE`, `provider_profile_id FK`, `model NULL` (buit → model per defecte del perfil), `max_tokens NULL`.
- **Resolucio** (`app/ai/tasks.py::resolve(task)`): config de la tasca (si el perfil esta actiu) → si no, primer perfil actiu; 409 si no n'hi ha cap. Els agents la fan servir per a CADA crida (extract i rank poden anar a proveidors diferents).
- Registre de tasques conegudes amb descripcio (cpv.extract, cpv.rank; creixera amb cada agent).
- API (`config:write`, tag ai): `GET /ai/tasks` (tasques conegudes + config actual + resolucio efectiva), `PUT /ai/tasks/{task}` (perfil, model?, max_tokens?), `DELETE /ai/tasks/{task}` (torna al comportament per defecte). Auditat.

### Pantalla (seccio a /admin/ai)

- «Configuracio per tasca»: fila per tasca amb descripcio, selector de perfil, camp de model (placeholder: el del perfil) i desa/restableix; mostra la resolucio efectiva actual.

## Fora d'abast

- Quotes diaries, fallback primari→secundari, parametres fins (temperatura, thinking) — seguents increments.

## Criteris d'acceptacio

- [x] Tasca configurada usa el perfil/model triats; sense config, primer perfil actiu.
- [x] Perfil desactivat o esborrat → fallback net.
- [x] Seccio a /admin/ai; bateries verdes.
