# Refinaments IA: agent revisor i informe d'auditoria programat (Estat: implementada)

## Context i objectiu

Tanca els dos punts oberts del roadmap F3: **agent revisor** del redactor documental (07 §2.3.4) i **informes periodics programables** de l'auditor (07 §2.2; job `reports.audit_monthly` de 08 §3).

## Comportament

### Agent revisor (tasca `doc.review`)

- `POST /doc-projects/{id}/documents/{doc_type}/actions/review/stream` (`tools:use`, propietat del projecte): rep TOTES les seccions redactades i emet, en streaming, una revisio en catala amb: coherencia entre seccions (contradiccions d'imports/durades/terminis), buits (seccions sense contingut o amb `[PENDENT: ...]`), repeticions i to; i una llista d'accions concretes per seccio.
- No reescriu res: es una segona opinio per a l'huma (human-in-the-loop). Registrat a ai_runs.
- Pantalla: boto «Revisa el document» al generador, al costat de «Revisió legal».

### Informe d'auditoria programat (`reports.audit_monthly`)

- Job mensual (interval 30 dies amb dedup mensual; el scheduler ja garanteix una sola execucio) que:
  1. calcula els red flags (SQL) i demana l'informe executiu a l'agent auditor;
  2. l'envia per correu als destinataris del parametre `reports.audit_recipients` (llista separada per comes; buit → no s'envia i es reporta);
  3. emet `audit.report_ready` a l'outbox (webhooks/n8n) amb el resum.
- Si el connector smtp esta desactivat o no hi ha perfil d'IA, el job ho reporta sense fallar (mai tomba el scheduler).
- Configurable des de /admin/config (parametre `reports.audit_recipients`) i llançable a ma amb el boto «Genera i envia a Intervencio» de la pantalla d'auditoria (`audit:run`). El scheduler tambe hi afegeix `sync.boe_norms` diari (08 §3).

## Fora d'abast

- PDF de l'informe (de moment cos de correu en Markdown/text); periodicitat configurable per UI.

## Criteris d'acceptacio

- [x] Revisor amb streaming (tasca doc.review) i boto al generador.
- [x] Job mensual + boto «Genera i envia a Intervencio»; reporta sense tombar (test) i emet audit.report_ready.
- [x] Botons a les pantalles; bateries verdes (414).
