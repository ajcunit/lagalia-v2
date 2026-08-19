# BACKLOG — LAGALia v2

Registre únic de tot allò que sorgeix durant el desenvolupament: idees, deute tècnic, desviacions de spec, peticions d'usuari i troballes. Funcionament i cicle de vida: [11-metodologia-specs.md](11-metodologia-specs.md) §3.

**Prioritats:** `P1` bloqueja la fase en curs · `P2` propera fase · `P3` millora quan es pugui.
**Estats:** `Proposta → Triada → Especificada → En curs → Feta` (o `Descartada`).

**Norma:** res no s'implementa des de `Proposta`. En passar a `Especificada` s'actualitzen les specs mestres afectades; en tancar-se, l'entrada enllaça la PR.

---

## Obertes

### B-002 · Contracte real del webhook Gestiona sense el token d'usuari al cos
- **Prioritat:** P3 · **Estat:** Proposta (posposada 2026-08-19: decisió de l'Esteve — la integració amb Gestiona es farà amb calma després del desplegament de test; el mòdul es pot activar quan arribi) · **Mida:** M
- **Descripció:** la v2 elimina l'enviament del `gestiona_access_token` personal dins del payload cap a n8n ([06-seguretat.md](06-seguretat.md) §2 fila 9), però cal validar amb l'entorn de proves de Gestiona quina alternativa funciona (credencial pròpia de n8n o token efímer d'abast mínim).
- **Com desenvolupar-la:** provar contra l'entorn de proves abans de la Fase 2; documentar el contracte definitiu a [08-hub-integracions.md](08-hub-integracions.md) §2.3 i escriure'n la spec de feature amb els contract tests que farà servir també el mode `n8n_bridge`.

### B-004 · Dataset d'or per avaluar el classificador CPV
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** M
- **Descripció:** [07-agents-ia.md](07-agents-ia.md) §5 preveu mesurar el pipeline CPV amb parells objecte→codi validats, però el dataset inicial no existeix.
- **Com desenvolupar-la:** extreure'l dels contractes històrics ja classificats de la v1 (mostra revisada manualment), i alimentar-lo després amb el feedback loop de la pròpia aplicació.


### B-007 · Idempotència persistent del header `Idempotency-Key`
- **Prioritat:** P3 · **Estat:** Proposta · **Mida:** S
- **Descripció:** el contracte declara `Idempotency-Key` als POST de creació ([openapi.yaml](../openapi.yaml)), però la implementació de la Fase 0 només s'empara en els `409` per duplicat (correu, codi). Falta la taula de claus usades amb resposta memoritzada i caducitat.
- **Com desenvolupar-la:** taula `idempotency_keys` (clau, hash de petició, resposta serialitzada, expiració) + dependency comuna; aplicar-la a tots els POST de creació.
- **Specs afectades:** [users-departments.md](../specs/users-departments.md), [05-api.md](05-api.md).

### B-008 · Dataset complet de contrasenyes filtrades
- **Prioritat:** P3 · **Estat:** Proposta · **Mida:** S
- **Descripció:** la política de contrasenyes rebutja una llista embeguda de contrasenyes habituals, però [openapi.yaml](../openapi.yaml) (`Password`) demana llistes de credencials filtrades. Cal un dataset offline (p. ex. subconjunt HIBP per freqüència) actualitzable, sense crides externes en la petició.
- **Com desenvolupar-la:** fitxer de hashos empaquetat amb la imatge o taula carregada per job; comprovació local a `app/core/security.py`.
- **Specs afectades:** [users-departments.md](../specs/users-departments.md), [06-seguretat.md](06-seguretat.md).

### B-010 · Seguiment d'ús de la plataforma (connexions, API, connectors, cues)
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** M
- **Descripció:** petició d'usuari (2026-08-12): un seguiment operatiu de què passa a la plataforma — connexions/sessions actives, ús de l'API (crides per identitat/endpoint/dia, ràtios d'error, rate limits assolits), crides a connectors externs (latència, errors, quota — ja previst a [08-hub-integracions.md](08-hub-integracions.md) §1) i estat de les cues (jobs encuats/en execució/fallits, temps d'espera). Part de la matèria primera ja existeix (`audit_log`, `jobs`, `sync_runs`, logs estructurats amb `trace_id`); falta agregar-la i exposar-la.
- **Com desenvolupar-la:** dues capes complementàries: (1) mètriques OpenTelemetry/Prometheus previstes a [03-arquitectura.md](03-arquitectura.md) §3 (comptadors per endpoint, connector i cua) per a Grafana; (2) un endpoint d'administració de resum (`/admin/usage`?) i pantalla a la zona d'Administració que consumeixi agregats de BD per a qui no tingui Grafana. Decidir retenció d'agregats (taula de comptadors diaris vs. només mètriques efímeres).
- **Specs afectades:** [03-arquitectura.md](03-arquitectura.md) §6, [08-hub-integracions.md](08-hub-integracions.md) §1, [10-ui.md](10-ui.md) §4 (zona Administració); spec de feature nova quan es triï.

### B-012 · Feedback del resultat dels jobs llançats des de la fitxa
- **Prioritat:** P2 · **Estat:** Parcialment resolta (sondeig implementat; queda la versió SSE) · **Mida:** S
- **Descripció:** el botó «Enriqueix» de la fitxa encua el job i avisa que està encuat, però l'usuari no sap si ha acabat, si ha fallat (p. ex. fases caducades a la font) ni quan cal recarregar. Detectat en ús real (2026-08-12): dos jobs fallits invisibles per a l'usuari.
- **Com desenvolupar-la:** subscriure la fitxa a l'SSE de progrés del job (`GET /jobs/{id}/events`, ja existeix amb token efímer) i, en acabar: refrescar les queries del contracte si èxit, o mostrar l'error del job si fallada. Reutilitzable per a exports i sync.
- **Specs afectades:** [contract-actions.md](../specs/contract-actions.md), [10-ui.md](10-ui.md).

### B-013 · Identitat de màquina completa per a escriptures
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** M
- **Descripció:** la fase 1 de les API keys ([specs/service-accounts.md](../specs/service-accounts.md)) cobreix els endpoints amb `Authorize(...)` (lectura); els d'escriptura usen la sessió d'usuari directament i responen 401 a una clau. Perquè n8n/agents puguin escriure (crear tasques, llançar syncs) cal estendre la identitat de màquina a `get_current_session` i als serveis que registren autoria.
- **Com desenvolupar-la:** actor unificat (usuari | màquina) a les dependències; autoria d'escriptures amb `actor_type agent` + id del service account a `audit_log` i als camps `created_by` (nullable o taula d'autoria); revisar cas per cas els serveis que llegeixen `user.id`/`user.departments`.

### B-018 · Estendre el selector de vista a tasques, adjudicataris i alertes
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** M
- **Descripció:** el selector de vista de la barra superior (specs/view-selector.md, 2026-08-19) ja governa contractes, menors i tauler; la resta de llistats (tasques de contracte, adjudicataris, alertes) continuen amb l'abast per defecte (tots els departaments de l'usuari) i no reaccionen a la tria.
- **Com desenvolupar-la:** afegir el paràmetre `view` (gramàtica `user|all|dept:<id>`, validació `resolve_view_scope`) als endpoints de llistat que filtren per departament i connectar-los al `ViewProvider` del frontend.
- **Specs afectades:** [view-selector.md](../specs/view-selector.md), specs dels mòduls afectats.

### B-019 · Aplicar els límits de petició d'API, IA i sincronització
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** S
- **Descripció:** detectat en preparar el desplegament (2026-08-19): `.env.example` declarava `RATE_LIMIT_API`, `RATE_LIMIT_AI` i `RATE_LIMIT_SYNC`, però només `RATE_LIMIT_LOGIN` existeix com a paràmetre i s'aplica ([06-seguretat.md](06-seguretat.md) §5 en preveu quatre). Les variables inexistents s'ignoraven silenciosament.
- **Com desenvolupar-la:** afegir els tres paràmetres a `app/core/config.py` i aplicar-los amb `enforce_rate_limit` als endpoints corresponents (API general per identitat, endpoints d'IA, llançament de sincronitzacions), amb test de límit assolit → 429.
- **Specs afectades:** [06-seguretat.md](06-seguretat.md) §5.

---

## Tancades

### B-003 · Decidir emmagatzematge d'objectes: sistema de fitxers o MinIO
- **Prioritat:** P2 · **Estat:** Resolta (2026-08-19: **MinIO** — ja muntat en un servidor; per al test es manté a la mateixa instància de LAGALia, `STORAGE_BACKEND=s3`) · **Mida:** S
- **Descripció:** [03-arquitectura.md](03-arquitectura.md) §2.6 deixa obert si els documents descarregats i generats van a disc muntat o a MinIO (S3).
- **Com desenvolupar-la:** l'abstracció ja existeix (`core/storage.py`, backends `filesystem` i `s3` seleccionables amb `STORAGE_BACKEND`; vegeu [specs/pscp-enrichment.md](../specs/pscp-enrichment.md)); queda només la decisió d'infraestructura per a producció segons la política de còpies municipal.

### B-005 · Abast del corpus normatiu inicial de l'assistent legal
- **Prioritat:** P2 · **Estat:** Resolta (2026-08-19: només **LCSP** el dia 1; la resta de normes s’afegeixen a mà des de la pestanya BOE de la configuració d’IA quan calgui) · **Mida:** S
- **Descripció:** cal fixar quines normes se subscriuen al connector BOE el dia 1 (LCSP i quines altres) i si s'inclou normativa autonòmica (DOGC) i instruccions internes de contractació.
- **Com desenvolupar-la:** llista acordada amb Secretaria/Intervenció; documentar-la a [07-agents-ia.md](07-agents-ia.md) §3bis i carregar-la com a dades inicials del connector.

### B-006 · Política de retenció i purga de dades
- **Prioritat:** P3 · **Estat:** Implementada (2026-08-19, specs/data-retention.md: purga diària `retention.purge`, terminis configurables per settings — auditoria 730 dies, IA 365 — acceptats per l'Esteve i ajustables segons indicacions del DPO) · **Mida:** S
- **Descripció:** [06-seguretat.md](06-seguretat.md) §7 fixa 2 anys d'auditoria i 1 any per a entrades/sortides d'IA com a valors per defecte, però han de ser validats per la responsable de protecció de dades de l'ajuntament.
- **Com desenvolupar-la:** validació formal, i implementar la purga com a job programat configurable.

### B-009 · Reintents amb backoff i dead-letter queue per a jobs
- **Prioritat:** P2 · **Estat:** Implementada (2026-08-18, specs/jobs-queue.md §B-009) · **Mida:** M
- **Descripció:** [03-arquitectura.md](03-arquitectura.md) §2.4 preveu reintents amb backoff exponencial i DLQ. La infraestructura de la Fase 0 (spec [jobs-queue.md](../specs/jobs-queue.md)) executa amb un sol intent; cal la política de reintents per tipus de job i la safata de morts amb re-encuat manual.
- **Com desenvolupar-la:** amb els primers jobs reals (sync Socrata, Fase 1): `max_tries` i backoff per tipus al registre de jobs, estat `dead` o taula/etiqueta DLQ, i endpoint d'administració per re-encuar.
- **Specs afectades:** [jobs-queue.md](../specs/jobs-queue.md), [03-arquitectura.md](03-arquitectura.md).

- **Cas real (2026-08-13):** un job `queued` agafat per un worker antic sense el handler queda zombi i el seu `dedup_key` bloqueja tots els encuaments següents; cal l'escombrat de jobs `queued` estancats (re-encuar o marcar `failed`) dins d'aquesta peça.

### B-011 · Normalització de noms d'adjudicatari a la ingesta i revisió de duplicats agrupada
- **Prioritat:** P2 · **Estat:** Resolta (specs/contractor-normalization.md; 2026-08-13, 223 parells genuïns restants en 147 grups revisables) · **Mida:** M
- **Descripció:** el primer sync real (2026-08-12, run 19) confirma la brutícia de la font: un mateix NIF apareix amb fins a **53 variants de nom** (puntuació, majúscules, «S.L» vs «S.L.»), cosa que crea un contractor per variant i fa esclatar els parells de duplicats de manera quadràtica (8.481 parells pendents — irrevisables un a un).
- **Com desenvolupar-la:** (1) normalització de noms a `resolve_contractor` abans de comparar (casefold, treure puntuació i formes societàries) perquè les variants trivials s'adjuntin al canònic com a àlies en lloc de crear contractor; (2) la pantalla de duplicats agrupa **per NIF** (un grup = un cas) en lloc de parells; (3) acció de fusió en bloc que converteix variants en `contractor_aliases`.
- **Specs afectades:** [contracts-sync.md](../specs/contracts-sync.md), [04-model-de-dades.md](04-model-de-dades.md) §2, [02-especificacio-funcional.md](02-especificacio-funcional.md) (duplicats d'adjudicatari).

### B-014 · Aïllament real entre bateria de tests i BD de desenvolupament
- **Prioritat:** P2 · **Estat:** Feta (2026-08-14) · **Mida:** M
- **Resolució:** `tests/conftest.py` recrea `lagalia_test` a cada sessió (DROP+CREATE+Alembic) i aïlla Redis a la db 1 amb FLUSHDB inicial; la BD i el Redis de dev queden intocables. Bateria 387/387 sense skips ni flakes (el de webhooks i el del scheduler-lock eren símptomes d'això).
- **Descripció:** els tests d'integració corren contra la BD de dev i, tot i les fixtures de save/restore, hi ha hagut fuites reals: `test_connector_hub` esborrava la fila del connector socrata (deixava el SuperBuscador i les syncs desactivats — arreglat el 2026-08-14 amb save/restore) i `test_webhooks::test_outbox_dispatch_signature_and_retry` falla intermitentment quan deliveries alienes creades durant la mateixa bateria vencen dins la finestra del test.
- **Com desenvolupar-la:** BD efímera per a la bateria (template database o schema per sessió de pytest amb Alembic al setup); mentrestant, endurir el test de webhooks perquè ignori tota delivery que no sigui del seu webhook també dins de `send_due_deliveries`.
- **Specs afectades:** [11-metodologia-specs.md](11-metodologia-specs.md) §tests.

### B-015 · Revisió visual i d'UX: menús, distribució de dades i jerarquia de la informació
- **Prioritat:** P1 · **Estat:** Feta (validada per l'Esteve 2026-08-17: fase 1 + fitxes amb pestanyes, carpetes de documents, icones lucide coherents i espaiats revisats a les tandes de contractes/adjudicataris/configuració) · **Mida:** L
- **Descripció:** petició de l'Esteve (2026-08-15): tractar els aspectes visuals i de millora d'UX de manera transversal — reformular els menús (les zones i entrades han crescut orgànicament: Operativa en té 6, Intel·ligència 5, Administració 8) i repensar la distribució de les dades i la informació a les pantalles (densitat, jerarquia, què es veu primer a cada vista, coherència entre llistats/fitxes/panells).
- **Com desenvolupar-la:** sessió de revisió pantalla a pantalla amb usuaris reals (aprofitar les proves de negoci en curs); proposta de navegació nova (agrupacions, ordre, possibles submenus o cercador d'accions); sistema de disseny consolidat (espaiats, mides de taula, targeta vs taula segons densitat); prototipar 2-3 pantalles clau (tauler, fitxa de contracte, llistat) abans d'estendre-ho. Mantenir WCAG 2.1 AA com a requisit de sortida de cada canvi.
- **Specs afectades:** [10-ui.md](10-ui.md) (revisió general), specs de pantalla existents a mesura que es toquin.

### B-016 · Xat general i xat per expedient
- **Prioritat:** P1 · **Estat:** Implementada (2026-08-17, specs/chat.md) · **Mida:** L
- **Descripció:** petició de l'Esteve (2026-08-17). Dues superfícies conversacionals:
  1. **Xat general**: conversa multi-torn amb l'assistent sobre la contractació de l'ens (evolució de l'analista de dades, que avui és pregunta-resposta d'un sol torn amb eines tancades).
  2. **Xat per expedient**: dins de la fitxa d'un contracte, poder «parlar de l'expedient» — l'assistent té el context d'aquell expedient (dades, pròrrogues, modificacions, criteris, mesa i **els seus documents indexats al RAG**) i respon amb citació de la font.
- **Com desenvolupar-la:** taules `chat_threads`/`chat_messages` (àmbit `general | contract`, `subject_id`, propietat per usuari amb abast departamental per al de contracte); reutilitzar el bucle d'eines de l'analista afegint historial de conversa i, per al xat d'expedient, una eina `get_contract_context(id)` + recuperació RAG filtrada als documents d'aquell expedient; streaming NDJSON i render Markdown ja existents; guardrails i comptabilitat a `ai_runs` com la resta d'agents. Decidir retenció i si les converses són privades o compartides per expedient (afecta LOPD: cap dada personal a les preguntes lliures).
- **Specs afectades:** [ai-analyst.md](../specs/ai-analyst.md) (evolució a multi-torn), [rag-service.md](../specs/rag-service.md), [10-ui.md](10-ui.md) (nova superfície a la fitxa de contracte), [07-agents-ia.md](07-agents-ia.md) §2.5.

### B-017 · Sincronitzar les publicacions de la fase d'execució (dataset 8idu-wkjv)
- **Prioritat:** P1 · **Estat:** Implementada (2026-08-18, specs/execution-sync.md) · **Mida:** M
- **Descripció:** endpoint aportat per l'Esteve (2026-08-17):
  `https://analisi.transparenciacatalunya.cat/api/v3/views/8idu-wkjv/` —
  «Contractació pública a Catalunya: publicacions de la fase d'execució a la PSCP».
  Per expedient/lot: `tipus_actuacio_execucio`, `denominacio_actuacio`, `data`,
  `data_fi`, `import_sense_iva`, adjudicatari (`identificacio`/`denominacio`),
  `observacions` i `url_json` de detall. Ompliria de veritat la pestanya
  «Execució» de la fitxa (avui només pròrrogues/modificacions del dataset RPC).
- **Com desenvolupar-la:** clau `dataset_execution` a la config del connector
  socrata; job `sync.execution` (filtre per `codi_ine10`, incremental si es pot)
  cap a una taula nova `contract_executions` (FK a contracts per file_code+lot,
  raw JSONB); font nova `execution` al mapejador de camps; targeta/llista a la
  pestanya Execució de la fitxa; el `url_json` es pot enriquir via connector
  pscp com les fases. Classificar `tipus_actuacio_execucio` i decidir si les
  pròrrogues d'aquest dataset substitueixen o complementen les del RPC.
- **Specs afectades:** remaining-syncs.md, field-mapping.md, contracts-ui.md,
  08-hub-integracions.md.

---

## Descartades

### B-001 · Mitigar debilitats crítiques de seguretat a la v1 mentre conviu amb la v2
- **Prioritat:** P1 · **Estat:** Descartada (2026-08-19: la v1 només estava en fase de test i s’apagarà; no queda exposada en producció) · **Mida:** S
- **Descripció:** la v1 continuarà en producció durant tot el projecte (~4 mesos). Dues debilitats permeten a qualsevol usuari autenticat robar secrets: `GET /api/config/` retorna API keys i tokens, i `/api/empleados/` exposa els tokens de Gestiona d'altres usuaris.
- **Com desenvolupar-la:** pegat mínim sobre la v1 — filtrar claus secretes a la resposta de config i eliminar els camps de token del schema d'empleat. No refactoritzar res més: la v1 està congelada funcionalment.
- **Specs afectades:** cap de la v2 (és manteniment de la v1); anotar el resultat a [06-seguretat.md](06-seguretat.md) §2 files 1-2.
