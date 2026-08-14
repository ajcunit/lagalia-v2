# Plataforma d'IA — fase 1: capa de proveidors (Estat: implementada)

## Context i objectiu

Primer increment de docs/07 (§1.1, §4): perfils de proveidor LLM registrables i administrables, amb comptabilitat de crides. Cap agent encara: aixo es el fonament que tots usaran.

## Comportament

### Model (migracio 0016, 04 §7)

- `ai_provider_profiles`: name UNIQUE, protocol (`openai_compatible|claude|gemini`), base_url, api_key xifrada (AES-256-GCM com les credencials del hub; write-only), default_model, capabilities JSONB, enabled, health_status, last_health_check.
- `ai_runs`: task, agent, provider_profile_id FK, model, input_summary (mai el prompt sencer amb dades), input_tokens, output_tokens, latency_ms, status (`success|error`), error_detail, user_id, trace_id, created_at. Tota crida LLM passa per aqui.

### Provider layer (`app/ai/providers.py`)

- Interficie unica `complete(messages, model?, json_schema?) -> CompletionResult` (contingut + tokens); adaptador generic **openai_compatible** (POST base_url + /chat/completions) i adaptador **claude** (API d'Anthropic, model per defecte claude-sonnet-5). Gemini queda per mes endavant (B-nnn si cal).
- TLS verificat sempre; timeout 120 s; les crides de treball van en jobs (les d'admin — healthcheck/models — son sincrones com el healthcheck de connectors).
- Cada crida registra `ai_runs` (exit o error) amb tokens i latencia.

### API (accio `config:write` per gestionar; tag `ai`)

- `GET /ai/providers` (api_key mai; `api_key_set`), `POST`, `PATCH /{id}` (enabled, base_url, default_model), `PUT /{id}/api-key` (write-only), `DELETE /{id}`.
- `POST /ai/providers/{id}/actions/healthcheck` — llista models (`/v1/models` o equivalent Claude) i persisteix salut; retorna els models detectats.
- `GET /ai/runs` (admin): keyset id desc, filtres task/status; panell d'execucions.

### Pantalla /admin/ai

- Targetes de perfil (com els connectors): alta (nom, protocol, base_url, model), api key write-only amb badge, prova de connexio que mostra els models detectats, activar/desactivar, esborrar amb confirmacio.
- Taula d'execucions (quan n'hi hagi): task, model, tokens, latencia, estat.

## Seguretat

- api_key xifrada, mai en respostes/logs (`api_key_set`). Guardrails de 07 §1.4 aplicaran als agents (fases seguents).

## Fora d'abast (increments seguents)

- Agents (CPV, auditor, redactor, legal, analista), RAG/pgvector, prompt registry, quotes, streaming.

## Criteris d'acceptacio

- [x] CRUD de perfils amb api key write-only; healthcheck retorna models reals.
- [x] ai_runs registra crides (test amb transport fals).
- [x] Pantalla /admin/ai completa; bateries verdes.
