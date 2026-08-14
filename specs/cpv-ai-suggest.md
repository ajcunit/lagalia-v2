# Agent classificador CPV (Estat: implementada)

## Context i objectiu

Primer agent de la plataforma (07 §2.1; A3 §3): donat l'objecte d'un contracte, top 5 de codis CPV amb score i justificacio en catala. Ruta: panell «Suggeriments amb IA» a `/cpv` (accio `tools:use`).

## Comportament

`POST /ai/cpv/suggest` `{text}` (sincron, interactiu; desviacio controlada com el provador — dues crides LLM curtes al perfil actiu):
1. Neteja de prefixos administratius i deteccio heuristica del tipus (servei|obra|subministrament) — sense LLM.
2. **Extraccio LLM** (prompt `cpv_extract` d'A3): paraules clau i divisions/codis candidats (JSON; neteja de <think>/``` com a fallback).
3. **Recuperacio lexica puntuada** sobre `cpv_codes` amb la taula de punts d'A3 §3.4 (codi exacte 10, divisio 5, prefix de tipus 5, parella de mots 5, prefix ampli 2, mot 1, difusa trigram 0.5; stemming catala simplificat).
4. Top 60 candidats → **re-ranquing LLM** (prompt `cpv_rank`) → top 5 `{code, description, score, justification}` validat; si el JSON falla, fallback al top lexic.
- El perfil de proveidor: el primer actiu (la configuracio per tasca arriba amb increments posteriors, 07 §4). Tot registrat a `ai_runs` (tasks `cpv.extract`, `cpv.rank`).

`POST /ai/cpv/feedback` `{query_text, chosen_code, suggested}`: registra la tria de l'usuari (migracio 0017, `ai_cpv_feedback`) — dataset d'or per a l'avaluacio continua (07 §5).

### Pantalla (dins /cpv)

- Panell «Suggeriments amb IA»: textarea de l'objecte + boto; resultats amb codi, descripcio, score, justificacio i boto «usa aquest» (copia el codi i envia feedback). Visible nomes si hi ha algun perfil d'IA actiu (si no, missatge que remet a /admin/ai).

## Fora d'abast (increments seguents)

- Taula editable de sinonims (A3 §3.5) i recuperacio vectorial (07 §2.1) — backlog; prompt registry versionat; configuracio proveidor-per-tasca; boto a la fitxa del contracte.

## Criteris d'acceptacio

- [x] Suggeriments reals contra el proveidor actiu amb expedients de l'ens.
- [x] Fallback lexic si el LLM falla; sense perfil actiu → 409 clar.
- [x] Feedback desat; bateries verdes.
