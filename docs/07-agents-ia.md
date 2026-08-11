# 07 — Plataforma d'agents d'IA

La v2 tracta la IA com una **plataforma transversal** amb agents especialitzats, no com a crides LLM disperses (v1: 3 prompts hardcoded a 2 serveis paral·lels Ollama/Gemini).

## 1. Arquitectura

```
            ┌────────────────────────────────────────────┐
            │              AGENT ORCHESTRATOR             │
            │  registre d'agents · quotes · traçabilitat  │
            └───┬─────────┬─────────┬─────────┬──────────┘
                │         │         │         │
        ┌───────▼──┐ ┌────▼─────┐ ┌─▼───────┐ ┌▼──────────┐
        │ CPV      │ │ Auditor  │ │ Redactor│ │ Analista  │
        │ Classif. │ │ red flags│ │ documental│ │ de dades │
        └───────┬──┘ └────┬─────┘ └─┬───────┘ └┬──────────┘
                │         │         │          │
        ┌───────▼─────────▼─────────▼──────────▼──────────┐
        │  SHARED SERVICES                                  │
        │  Provider layer (Ollama/Gemini/Claude)            │
        │  RAG (pgvector) · Tool layer (API interna, scopes)│
        │  Prompt registry (versionat) · Output validation  │
        └───────────────────────────────────────────────────┘
```

### 1.1 Provider layer
- Interfície única: `complete(task, messages, schema?, stream?)`.
- **Protocol primari: API compatible OpenAI** (`/v1/chat/completions` + `/v1/embeddings` + `/v1/models`). Un sol adaptador genèric configurat amb `base_url` + `api_key` + `model` cobreix d'un cop: OpenAI, Azure OpenAI, **Ollama** (endpoint `/v1` natiu), vLLM, LM Studio, LiteLLM, OpenRouter, Mistral, DeepSeek... — qualsevol servidor actual o futur que parli aquest protocol, sense tocar codi.
- **Adaptadors natius addicionals** només on el protocol OpenAI no arriba o es vol el tret diferencial del proveïdor: **Gemini** i **Claude API** (recomanat per a redacció documental de qualitat: `claude-sonnet-5` per redacció, `claude-haiku-4-5` per classificació massiva).
- **Perfils de proveïdor**: es poden registrar N instàncies (p. ex. "Ollama local", "vLLM del CPD", "OpenRouter") cadascuna amb les seves credencials xifrades; cada **tasca** referencia un perfil+model+paràmetres (temperatura, max tokens, mode raonament). Fallback opcional (si el perfil primari falla → secundari).
- Capacitats declarades per perfil (streaming, JSON mode, tool use, embeddings, visió): l'orquestrador les comprova abans d'assignar una tasca.
- Sortides estructurades: quan la tasca ho requereix, validació contra JSON Schema amb reintents automàtics.
- Comptabilitat: tokens i latència per crida a `ai_runs`; quotes per agent/dia.

### 1.2 Prompt registry
- Prompts com a plantilles versionades a BD (`ai_prompt_versions`) amb variables tipades documentades; edició des de la UI d'admin (com v1) però amb historial, difs i possibilitat de rollback.
- Cada `ai_run` referencia la versió exacta → reproduïbilitat.

### 1.3 Tool layer (agents que consumeixen l'API)
Els agents amb capacitat d'acció (analista) no toquen la BD: criden l'**API pròpia** amb un service account d'scopes mínims (`contracts:read`, `audit:read`). Les eines exposades a l'agent són funcions tancades (cerca de contractes, agregacions, red flags), no SQL lliure.

### 1.4 Guardrails comuns
- Dades externes delimitades al prompt com a contingut no fiable (anti prompt-injection).
- Cap escriptura sense acceptació humana; el botó "acceptar" registra `accepted_by`.
- Streaming de tokens a la UI per a tasques llargues (redacció).
- Traçabilitat completa i pantalla d'admin "Execucions d'IA" (cost, latència, taxa d'acceptació per agent — mètrica de qualitat real).

## 2. Agents

### 2.1 Classificador CPV
Evolució del pipeline híbrid v1 (que funciona bé i es conserva com a esquelet):
1. Neteja del text i detecció del tipus de contracte (heurístic, sense LLM).
2. **Recuperació híbrida**: lèxica ponderada sobre `cpv_codes` (trigram + stemming català + sinònims — ara taula editable, no diccionari hardcoded) **+ embeddings** de les descripcions CPV (pgvector) — millora el recall respecte la v1.
3. Re-rànquing LLM (sortida JSON validada): top 5 amb `score` i justificació en català.
4. Feedback loop: el codi finalment triat per l'usuari s'enregistra → dataset d'avaluació per mesurar i millorar el pipeline.

### 2.2 Auditor (anàlisi de dades / red flags)
- Els red flags deterministes (fraccionament, baixes temeràries, concurrència, caducitats) es calculen amb SQL — la IA no inventa números.
- L'agent rep els resultats + context (sèries temporals, comparatives per departament) i genera l'informe executiu amb riscos prioritzats i recomanacions; suporta prompt addicional de l'interventor.
- **Noves capacitats v2**: preguntes ad-hoc en llenguatge natural ("evolució de la despesa en serveis del departament X, 3 anys") → l'agent tradueix a crides a l'API d'estadístiques i redacta la resposta amb les dades reals adjuntes (mai xifres generades pel model); informes periòdics programables (job mensual → PDF + email a Intervenció).

### 2.3 Redactor documental (PPT/PPA/Informes)
Correcció del defecte principal v1 (generava seccions sense mirar les referències):
1. **Ingesta**: els documents de referència del cartipàs (plecs històrics propis o del SuperBuscador) s'indexen al RAG (extracció PyMuPDF → chunking per secció → embeddings).
2. **Índex**: proposta d'estructura a partir de les referències + plantilles per tipus (PPT/PPA/Informe) mantingudes per l'admin.
3. **Redacció per secció**: recuperació dels chunks rellevants per al títol+instruccions → redacció amb citació de les fonts usades (traçable a la UI: "basat en: PPT expedient 2024/123 §4").
4. **Revisió**: agent revisor opcional (coherència entre seccions, requisits legals bàsics de la LCSP com a checklist).
5. **Export server-side**: DOCX real (python-docx) i PDF, amb plantilla corporativa de l'ajuntament.

### 2.4 Assistent legal / verificador de compliment (nou)
Comprova que els expedients i els documents generats passen els filtres de la normativa de contractació pública. Dues capes, com l'auditor:

1. **Motor de regles determinista** (sense LLM, sempre exacte): llindars i límits de la LCSP codificats com a regles versionades i datades — imports màxims del contracte menor (15.000 € serveis/subministraments, 40.000 € obres), durada màxima del menor (1 any, sense pròrroga), llindars d'harmonització, procediment adequat a l'import, terminis de publicitat, percentatges de garantia, límits de modificació (art. 203-207), incompatibilitats de fraccionament. Cada regla referencia l'article concret. Quan la norma canvia, es versiona la regla amb data d'efecte (els expedients antics es validen amb la norma vigent aleshores).
2. **Revisió LLM amb RAG normatiu**: sobre el text dels plecs (generats o pujats) executa una checklist de conformitat (contingut mínim del PCAP/PPT, criteris d'adjudicació vàlids, clàusules obligatòries — socials, mediambientals, protecció de dades) recuperant els articles aplicables del corpus normatiu indexat (vegeu §3bis) i **citant sempre article i enllaç al text consolidat**.

- **Sortida**: informe de conformitat amb semàfor per comprovació (`conforme | avís | no conforme | no verificable`), justificació i referència normativa navegable; s'adjunta a l'expedient i queda a `ai_runs`.
- **On s'executa**: sota demanda a la fitxa del contracte ("Revisió legal"), com a pas suggerit abans d'exportar un document del generador, i en batch sobre el pla anual (detecta p. ex. menors planificats que superarien llindars).
- **Límits explícits**: és suport a la revisió — no substitueix l'informe jurídic preceptiu de Secretaria; la UI ho indica i cap resultat bloqueja res automàticament (human-in-the-loop, com tota la plataforma).

### 2.5 Analista de dades (nou)
- Xat sobre el corpus de contractació amb eines tancades: `search_contracts`, `aggregate`, `get_stats`, `get_red_flags`, `compare_periods`.
- Respostes sempre amb la taula/dades font adjunta i enllaços als expedients; exportable a informe.
- Pensat també per a consum extern via API (`POST /ai/analyses`) per n8n o altres agents municipals.

## 3. RAG (servei compartit)

- Corpus: documents de fase descarregats (PCAP, PPT, memòries...), documents pujats manualment i el corpus normatiu (§3bis).
- Pipeline: descàrrega → object storage → extracció de text → chunking (~800 tokens amb solapament, respectant seccions) → embeddings via `/v1/embeddings` de qualsevol perfil compatible OpenAI (local o cloud) → `rag_chunks`.
- Recuperació híbrida: BM25/trigram + cosinus, amb filtre per metadades (tipus de document, expedient, any).
- Indexació com a job asíncron subscrit a `contract.updated`/descàrrega de documents; estat visible per document (`indexed_at`).

## 3bis. Corpus normatiu (alimentat pel connector BOE)

- **Normes subscrites** (LCSP — Llei 9/2017 —, RGLCAP, reglaments de llindars UE, instruccions internes de contractació) descarregades en **text consolidat** via el connector `boe` ([08-hub-integracions.md](08-hub-integracions.md) §2.7), amb chunking per article i metadades (norma, article, versió de consolidació, data de vigència).
- Quan el BOE publica una modificació d'una norma subscrita: re-descàrrega del consolidat, re-indexació, **avís als admins** i marca de revisió sobre les regles deterministes afectades del verificador legal.
- Les respostes de l'assistent legal citen sempre (norma, article, versió) amb enllaç al text oficial.

## 4. Configuració (UI d'admin)

- Interruptor mestre + per agent (equival als mòduls v1).
- Gestió de perfils de proveïdor: alta d'un endpoint compatible OpenAI (base URL, key, models disponibles autodetectats via `/v1/models`), prova de connexió, estat de salut.
- Per tasca: perfil de proveïdor, model, paràmetres, quota diària.
- Editor de prompts amb versions.
- Panell d'execucions: filtres per agent/usuari/estat, cost acumulat, taxa d'acceptació.

## 5. Avaluació contínua

- Dataset d'or per al CPV (parells objecte→codi validats pels usuaris) amb mètrica top-5 accuracy executada a CI quan canvia prompt o model.
- Revisió mostral mensual de les sortides de l'auditor i el redactor (checklist humana registrada).
