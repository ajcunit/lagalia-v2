# Annex A3 — Prompts d'IA i pipeline CPV (base v1)

Transcripció dels prompts per defecte de la v1 i de la lògica del pipeline CPV, per no dependre del codi antic. A la v2 aquests textos són la **versió 1 del registre de prompts** (`ai_prompt_versions`), editables i versionats des de la UI ([07-agents-ia.md](../07-agents-ia.md) §1.2).

## 1. Prompts per defecte (v1, literals)

### `cpv_extract` — extracció de paraules clau i candidats
```
Ets un expert en CPV europeu. Per aquest objecte de contracte:
"{description}"

1. Extrau 4-6 paraules clau en català.
2. Identifica les 2 DIVISIONS (2 primers dígits) més probables.
3. Suggereix 3 CODIS CPV (8 dígits) concrets.

Respon NOMÉS amb:
Paraules: p1, p2...
Divisions: 00, 00
Codis: 00000000, 00000000...
```
Variables: `{description}`.

### `cpv_rank` — re-rànquing de candidats
```
You are an expert in European CPV classification (Reg. 213/2008).
Rank candidates for the contract description. Select the most specific code.
Return JSON array: [{"codigo","descripcion","score","justificacion"}].
```
Variables: descripció del contracte + llista de candidats (injectats pel servei). Es crida amb mode JSON del proveïdor. La justificació s'espera en català.

### `audit` — informe d'auditoria
```
Ets un auditor expert en contractació pública. Analitza:
{data}

{custom_prompt}

Proporciona informe en català amb Markdown.
```
Variables: `{data}` (top 5 de cada red flag), `{custom_prompt}` (text lliure de l'usuari, opcional).

> ⚠️ A la v2, `{data}` i `{custom_prompt}` s'han de delimitar explícitament com a contingut no fiable dins el prompt (anti prompt-injection, [06-seguretat.md](../06-seguretat.md) §6).

### Prompts del generador documental (v1, dins `ppt_service`)
- **Índex**: rol "consultor expert en redacció de plecs tècnics (PPT)", context = text extret de fins a **3 documents**, **15 pàgines** cadascun, truncat a **10.000 caràcters**; sortida `[{"title": ...}]`. Fallback de 5 seccions si el parsing falla.
- **Secció**: rol "redactor tècnic expert en sector públic (català)", to legal, sortida Markdown.

> ⚠️ Defecte v1 a corregir: el prompt de secció **no rep** el contingut dels documents de referència (les URLs es passen però no s'usen). A la v2 la secció es redacta amb els chunks recuperats per RAG i cita les fonts.

## 2. Neteja de resposta (aplicable a qualsevol proveïdor)

1. Eliminar blocs `<think>`, `<thought>`, `<thinking>` (models amb raonament visible).
2. Eliminar el marcatge de bloc Markdown (```json ... ```).
3. Per a JSON: extreure des del primer `[` fins a l'últim `]`.

A la v2 això es substitueix, quan el proveïdor ho suporta, per **sortida estructurada validada contra JSON Schema** amb reintent automàtic; la neteja queda com a fallback.

## 3. Pipeline híbrid de classificació CPV (lògica v1 a conservar)

1. **Neteja de la descripció**: eliminar prefixos administratius de l'objecte del contracte.
2. **Detecció del tipus de contracte** per heurística de paraules clau amb puntuació: `servei` | `obra` | `subministrament`.
3. **Extracció LLM** (prompt `cpv_extract`) → paraules clau, divisions i codis candidats.
4. **Recuperació lèxica sobre el diccionari CPV local**, amb aquestes puntuacions:

| Senyal | Punts |
|---|---|
| Codi exacte suggerit pel LLM | 10.0 |
| Arrel de divisió suggerida | 5.0 |
| Prefix del tipus de contracte detectat | 5.0 |
| Parella de paraules clau (amb stemming) | 5.0 |
| Prefix ampli | 2.0 |
| Paraula clau individual | 1.0 |
| Coincidència difusa (70% del mot) | 0.5 |

5. **Expansió de sinònims** (v1: diccionari hardcoded amb termes com furgoneta, gossera, software, platja, vela, climatització, vials, grua, patrocini). **A la v2 ha de ser una taula editable**, no codi.
6. **Stemming català** simplificat: regles de plural i derivats (`-es`, `-ons`, `-ns`, `-s`, `-iva`, `-iu`).
7. **Top 60 candidats** → re-rànquing LLM (prompt `cpv_rank`) → **top 5** amb `score` i justificació.

Millores previstes a la v2 ([07-agents-ia.md](../07-agents-ia.md) §2.1): afegir recuperació vectorial (embeddings de les descripcions CPV) a la fase 4, i feedback loop amb el codi finalment triat per l'usuari.

## 4. Paràmetres de generació (v1)

| Proveïdor | Paràmetres |
|---|---|
| Ollama | `think` heurístic: models `gpt-oss*` → `"low"`; `deepseek-r1`/`qwen3` → `False`; altres → omès. Models configurables per tasca (CPV, auditoria) |
| Gemini | `temperature 0.1`, `topK 1`, `topP 1`, `maxOutputTokens 2048`; model per defecte `gemini-1.5-flash` |

A la v2 aquests paràmetres es defineixen **per tasca** al perfil de proveïdor, no globalment.
