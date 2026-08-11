# 06 — Seguretat per disseny

Marc de referència: **ENS nivell mitjà** + OWASP ASVS L2. Aquest document fixa els controls de la v2 i mapeja les debilitats detectades a la v1 amb la seva correcció estructural.

## 1. Model d'amenaces (resum)

| Actiu | Amenaces principals |
|---|---|
| Dades de contractació + dades personals (empleats, adjudicataris) | accés no autoritzat (IDOR), exfiltració, alteració no traçada |
| Credencials de tercers (Gestiona, Gemini, LDAP) | robatori des de BD/config/API, MITM, exfiltració via webhook |
| Integracions sortints | SSRF, injecció a consultes de tercers (SoQL), URLs de webhook malicioses |
| Sortides d'IA | prompt injection des de dades públiques sincronitzades, decisions no supervisades |
| Disponibilitat | jobs desbocats, abús d'endpoints costosos (sync, LLM) |

## 2. Debilitats v1 → correcció v2

| # | Debilitat v1 | Correcció v2 (per disseny) |
|---|---|---|
| 1 | `GET /config/` retorna tots els secrets a qualsevol autenticat | `settings` amb `is_secret`: valors xifrats, API write-only (`is_set`), lectura només de claus no secretes i amb scope `config:read` |
| 2 | Schema `Empleado` exposa tokens Gestiona de tercers | credencials a `user_credentials` xifrades; mai serialitzades; endpoints d'usuari amb DTOs mínims |
| 3 | IDOR a detalls (`/contratos/{id}`, historial, menors...) | autorització centralitzada avaluada a **cada** recurs, també en detalls i subrecursos (vegeu §3); tests automàtics d'IDOR per a tot endpoint amb `{id}` |
| 4 | Endpoints sense auth (`/adjudicatarios/duplicados/lista`, `/proxy-json`) | *deny by default*: middleware exigeix identitat a tot `/api` excepte llista blanca explícita (`/health`, `/setup/status`); test de CI que verifica que cap ruta queda fora |
| 5 | `X-View-Mode` controlat pel client | el mode de vista és un paràmetre avaluat pel motor d'autorització contra el rol real; no altera mai l'abast màxim permès |
| 6 | SoQL injection (superbuscador, sync per `codi_ine10`) | connector Socrata amb query builder parametritzat i validació estricta d'entrades (`codi_ine10` = `^\d{10}$`, dates ISO) |
| 7 | SQL cru amb f-strings (adjudicataris) | SQLAlchemy Core/ORM amb bind params; prohibit `text()` amb interpolació (regla de lint) |
| 8 | `verify=False` a totes les crides Gestiona | TLS verificat sempre; si el certificat és intern, CA bundle configurable — mai desactivar la verificació |
| 9 | Webhook n8n rep el token Gestiona de l'usuari en el cos, URL lliurement configurable | URL de webhook validada (https, no IP privada — anti-SSRF), signada amb secret propi; el token de Gestiona **no viatja** al cos: el flux es re-dissenya perquè n8n usi credencial pròpia o un token efímer d'abast mínim |
| 10 | `SECRET_KEY` autogenerada en calent / default `changeme` | arrencada **falla** si falten secrets obligatoris en producció; validació de fortalesa; rotació documentada |
| 11 | Validation handler retorna/loga el cos de la petició | Problem Details sense eco del cos; logs amb redacció automàtica de camps sensibles |
| 12 | JWT per query string a SSE (i acceptat a tot arreu) | tokens efímers d'un sol ús per a SSE/descàrregues; el JWT només s'accepta a `Authorization` |
| 13 | Refresh sense detecció de reutilització; desactivar usuari no revoca tokens | famílies de refresh tokens (reús → revocació de família); desactivació d'usuari revoca família i sessions |
| 14 | Auditoria només al login; sense endpoint de consulta | `audit_log` append-only amb cadena de hash, cobertura d'escriptures i accions sensibles, consulta per a admins ([04-model-de-dades.md](04-model-de-dades.md) §9) |
| 15 | Rate limit per IP directa (trenca darrere proxy) | límits amb `X-Forwarded-For` de proxy de confiança + límits per identitat (usuari/API key), backend Redis |
| 16 | Sense CSP/HSTS | vegeu §5 |
| 17 | Password policy només al setup; sense bloqueig | política única a tot arreu (≥12 caràcters + comprovació contra llistes de filtrades), lockout progressiu, `check_needs_rehash` d'Argon2 |
| 18 | `POST /cpv/sync` i similars sense rol | tota operació costosa exigeix scope (`sync:execute`) i té quota |

## 3. Autorització centralitzada

Un únic mòdul `authz` (policy engine intern, estil Oso/Casbin o implementació pròpia declarativa):

```
allow(actor, action, resource) si
  actor té scope(action)                        # capacitat
  i abast(actor) cobreix resource               # departaments / propietat
  i regles específiques (p. ex. dept_manager només PATCH de warning_months)
```

- **Cap `if rol == ...` als routers** (la v1 en tenia a 6 llocs amb divergències). Dependency única `Authorize(action)` injectada per endpoint, resource loader que aplica el filtre departamental també a llistats.
- Matriu de permisos versionada com a **taula de veritat testejada** (pytest parametritzat rol × acció × abast).
- Agents d'IA i service accounts passen pel mateix motor amb els seus scopes; mai personifiquen usuaris.

## 4. Secrets i credencials

- **Jerarquia**: (1) variables d'entorn / fitxer de secrets de Docker per als secrets d'infra (`DATABASE_URL`, `SECRET_KEY`, clau de xifrat); (2) **xifrat aplicatiu** (AES-256-GCM via `cryptography`, clau mestra `ENCRYPTION_KEY` amb suport de rotació per versió de clau) per a secrets operatius guardats a BD (API keys de proveïdors IA, addon token Gestiona, credencials de connectors, tokens per usuari).
- Mai secrets: al repositori, a logs, a respostes d'API, a payloads de webhook.
- Inventari de secrets al README d'operacions amb procediment de rotació per a cadascun.

## 5. Seguretat perimetral i de transport

- TLS obligatori (Caddy/Nginx davant; HSTS `max-age=31536000; includeSubDomains`).
- Capçaleres: CSP estricta per a l'SPA (`default-src 'self'`; sense inline scripts — build compatible), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`; `Cache-Control: no-store` a `/api`.
- CORS: llista d'orígens explícita per entorn; mai `*` amb credencials.
- Rate limiting per capes: login 5/min/IP + 20/h/compte; API general per identitat; endpoints LLM i sync amb quotes específiques; respostes 429 amb `Retry-After`.
- Proxy de contingut extern (`/public-registry/phase`): whitelist de dominis + revalidació post-redirect (mantenir el disseny v1, que era correcte) + autenticació + límit de mida de resposta.

## 6. Seguretat de la plataforma d'IA

- **Entrades no fiables**: tot text provinent de fonts externes (objectes de contracte, PDFs públics) es tracta com a *untrusted input* — els prompts el delimiten explícitament i les sortides es validen contra esquema (JSON Schema) abans d'usar-se.
- **Cap escriptura automàtica**: les sortides d'IA són sempre *suggeriments* pendents d'acceptació humana registrada (`ai_runs.accepted_by`).
- **Egress control**: amb proveïdor local (Ollama) cap dada surt; amb proveïdors cloud (Gemini/Claude), configuració explícita de quines tasques poden sortir i amb quines dades (per defecte, mai dades personals d'empleats).
- Quotes de tokens/dia per agent i alertes de despesa.
- Registre complet per a auditoria (model, prompt version, entrada, sortida, cost) — vegeu [07-agents-ia.md](07-agents-ia.md).

## 7. Dades personals (RGPD)

- Minimització: dels empleats només nom, email, DNI (necessari per a Gestiona) — DNI xifrat a BD.
- Registre d'activitats de tractament documentat; base jurídica: missió d'interès públic.
- Retenció: logs d'auditoria 2 anys (configurable); `ai_runs` amb purga d'entrades/sortides a 1 any mantenint metadades.
- Drets ARSOPL: export i esborrament lògic d'usuari per endpoint d'admin.

## 8. Cadena de subministrament i desplegament

- Dependències fixades (`uv`/`pip-tools` lockfile; `npm ci`); Dependabot/Renovate; `pip-audit` + `npm audit` a CI; SBOM (syft) per release.
- Imatges: usuari no-root, read-only filesystem on sigui possible, healthchecks, escaneig (trivy) a CI.
- CI amb: lint de seguretat (bandit, semgrep amb regles pròpies — p. ex. prohibir `verify=False` i `text(f"...")`), tests d'autorització, contract testing.
- Backups xifrats amb prova de restauració mensual documentada.

## 9. Registre i monitoratge de seguretat

- Esdeveniments de seguretat (logins fallits repetits, 403 en ràfega, ús d'API keys des d'IP noves, canvis de configuració) → log estructurat amb severitat + notificació per email/webhook a l'admin.
- Mètriques exposades: intents de login, 401/403/429 per endpoint, edat de secrets, estat de connectors.
