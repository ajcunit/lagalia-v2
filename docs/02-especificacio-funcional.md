# 02 — Especificació funcional (paritat amb la v1)

Inventari complet de funcionalitats de l'aplicació actual (LAGALia Contractació v1: FastAPI + React). És el **contracte de paritat** de la v2: tot el que hi ha aquí s'ha de conservar, tret del que es marca explícitament com a ~~descartat~~ o 🔁 *redissenyat*.

---

## 1. Actors i rols

| Rol | Capacitats |
|---|---|
| `admin` | Accés total: configuració, usuaris, departaments, sincronitzacions, validacions, edició completa de contractes |
| `responsable_contratacion` | Com admin excepte configuració del sistema i gestió d'usuaris; sincronitzacions, assignacions massives, edició completa de contractes, duplicats |
| `responsable` | Veu contractes del seu departament; edita només `meses_aviso_vencimiento`; pot finalitzar/descartar finalització dels contractes on és responsable |
| `empleado` | Consulta contractes del seu departament |

**Flags addicionals independents del rol:** `permiso_auditoria` (accés al mòdul d'auditoria/red flags), `permiso_pla_contractacio` (accés d'edició al pla anual).

**Vista dual:** `admin` i `responsable_contratacion` poden alternar entre *Vista Admin* (tots els departaments) i *Vista Usuari* (només els seus). 🔁 A la v2 el mode de vista no pot ser una capçalera controlada pel client (`X-View-Mode`): serà un paràmetre de consulta explícit validat pel motor d'autorització.

**Multi-departament:** un empleat pot pertànyer a N departaments (M2M); un contracte pot estar assignat a N departaments i tenir N responsables.

**Matriu completa de permisos** (acció × rol × abast, amb les divergències v1→v2): [annexos/A2-matriu-permisos.md](annexos/A2-matriu-permisos.md).

## 2. Mòduls funcionals

### 2.1 Setup inicial
- Detecció automàtica de sistema no inicialitzat (`0 usuaris`) amb redirecció a un assistent.
- Wizard de 4 passos: benvinguda → creació d'admin (validació de contrasenya: ≥8, majúscula, minúscula, número, amb indicador de força) → dades d'organització (nom, codi INE10, opcional) → confirmació.
- Crea l'admin, la configuració per defecte (endpoints de sincronització, IA desactivada, prompts per defecte) i redirigeix al login.

### 2.2 Autenticació i perfil
- Login email + contrasenya (local, Argon2id) **o LDAP/Active Directory** (si està habilitat): bind + cerca per `sAMAccountName`, provisió automàtica d'usuaris i **mapeig de grups AD → rol + departament**.
- Tokens JWT d'accés (30 min) + refresh token opac amb rotació (7 dies), revocació al logout.
- Perfil propi: edició de nom, DNI i contrasenya (email i rol només lectura).
- **Vinculació personal amb Gestiona** en 3 passos: generar autorització (l'usuari accepta termes a Gestiona) → comprovar estat i recollir `access_token` → vincular per DNI per obtenir `gestiona_user_id`.

### 2.3 Dashboard
- KPIs: total contractes (+nous del mes), contractes amb fi propera, possiblement finalitzats, volum total adjudicat, total i volum de contractes menors, licitadors únics. Cada targeta enllaça al llistat filtrat corresponent.
- Filtres del dashboard: any, import mínim/màxim.
- Gràfic de barres horitzontals apilades **Top 10 adjudicataris** (desglossament per expedient al tooltip; clic → llistat filtrat).
- Gràfic semicircular **contractes per departament** (clic → llistat filtrat).
- Resum per estat clicable.
- Dades calculades al backend però no mostrades a la v1 (🔁 mostrar-les a la v2): renovacions crítiques, contractes finalitzats pendents, temps mitjà de tramitació, pendents d'aprovació.

### 2.4 Contractes (majors)
**Llistat**
- Filtres: cerca lliure (expedient/objecte/adjudicatari), departament, exercici, tipus, estat actual (incloent "Sense estat"), procediment, rang de dates d'inici, rang d'imports, adjudicatari (nom o NIF), CPV, estat intern, prorrogables, alerta de finalització, possiblement finalitzats, sense departament assignat.
- **Deduplicació per expedient**: un representant per `codi_expedient` amb comptadors de lots, pròrrogues i modificacions.
- Ordenació server-side per qualsevol camp; paginació 50/100/200/500; estat de filtres persistit a la URL (el botó Enrere restaura cerques).
- Selecció múltiple amb barra flotant: **assignació massiva de departament** i exportació CSV de la selecció.
- Exportació CSV (`;`, UTF-8 amb BOM) del conjunt filtrat.

**Detall d'expedient**
- Capçalera amb badges d'estat intern i estat actual; accions: veure publicació oficial, anar/obrir a Gestiona, enriquir, editar.
- Alertes de venciment: vermella (possiblement finalitzat, amb accions *Finalitzar* / *Descartar*) i groga (fi propera, finestra configurable).
- Seccions: objecte; gestió interna (departaments, responsables — filtrats per pertinença al departament i rol —, estat intern, mesos d'avís); adjudicatari (nom, NIF, nacionalitat, tipus d'empresa, tercer sector, telèfon, email); imports (licitació/adjudicació amb i sense IVA, pressupostos, valor estimat); organisme i procediment; dates i durada; classificació (CPV múltiples amb descripció resolta, NUTS, lots, finançament); **lots de l'expedient** (acordions); **pròrrogues** i **modificacions**; seccions enriquides: criteris d'adjudicació (amb ponderació), mesa de contractació, **documents de l'expedient per fase** (amb descàrrega i botó "usar com a plantilla" per al generador documental), informació contractual (normativa, garanties, harmonitzat, subcontractació, ofertes rebudes...), peu de recurs.
- Edició inline amb matriu de permisos per rol (§1); tot canvi manual queda a l'historial.
- Historial de canvis per contracte (camp, valor anterior/nou, usuari, tipus: sincronització/manual/validació/webhook).

**Creació manual**
- Formulari: objecte, tipus, estat inicial, adjudicatari (nom/NIF), preu de licitació, departaments i responsables.
- Si la integració Gestiona és activa: codi d'expedient autogenerat provisional (`PENDENT-...`) i acció **"Obrir a Gestiona"** que crea l'expedient real via webhook i renombra el local amb el codi retornat.

**Transicions d'estat intern:** `normal → pendiente_aprobacion → aprobado | rechazado`; a més `estat_actual → 'Finalitzat'` per acció manual.

### 2.5 Contractes menors
- Sincronitzats des del Registre Públic de Contractes (procediment "Menor"), amb fusió del registre d'adjudicació i el de **liquidació** per expedient.
- Llistat amb filtres (cerca, adjudicatari, exercici, departament, estat intern, recents, sense assignar), selecció múltiple i assignació massiva, exportació CSV.
- Detall: dades d'expedient, bloc de liquidació (tipus, data, import), imports, durada (anys/mesos/dies), departaments editables (admin / resp. contractació).

### 2.6 Adjudicataris
- Rànquing unificat (majors + menors) amb nombre de contractes i import total; ordenació server-side; cerca per nom o CIF; paginació amb total real.
- Detall d'empresa: NIF, KPIs, històric complet de contractacions (majors i menors) navegable.
- **Normalització de noms**: taula d'àlies (`nom original → nom canònic`) aplicada durant la sincronització; gestió de **duplicats d'adjudicatari** (mateix NIF, nom diferent) amb fusió que actualitza tots els contractes passats i futurs. 🔁 La v1 no genera mai les deteccions (només les gestiona); la v2 ha d'incloure el detector (agrupació per NIF a cada sincronització).

### 2.7 Duplicats de contractes
- Detecció automàtica durant la sincronització: mateix `codi_expedient` + `estat_actual` + `lots` → parell marcat `pendiente_aprobacion`.
- Cua de validació amb comparativa costat a costat (objecte, adjudicatari, imports, dates d'actualització) i observacions.
- Accions: aprovar A, aprovar B, fusionar (guanya el més recent per `data_actualitzacio`), rebutjar ambdós. Registre de qui valida i quan.
- Badge de pendents al menú (contractes + adjudicataris).

### 2.8 Sincronització i enriquiment
- **4 processos amb progrés en temps real** (SSE a la v1; 🔁 v2: jobs asíncrons amb subscripció d'estat):
  1. Contractes majors des de Transparència Catalunya (Socrata, filtrat per `codi_ine10`), amb detecció de canvis per hash, herència de departaments entre lots del mateix expedient, regles d'associació automàtica, detecció de duplicats i enriquiment automàtic dels nous.
  2. Contractes menors + liquidacions.
  3. Diccionari CPV (4 nivells: Divisió/Grup/Classe/Categoria amb jerarquia).
  4. **Enriquiment** històric en batch des de contractaciopublica.cat (JSONs de fase → ~35 camps addicionals, criteris, mesa, documents), amb throttling respectuós i mode `force`.
- Sincronització de **pròrrogues i modificacions** (propaguen la nova data de fi al contracte).
- **Programador (cron)**: sincronització automàtica diària configurable (hora, dies de la setmana, zona horària), recarregable en calent.
- Historial de sincronitzacions: data, estat (en procés/exitosa/fallida/parcial), comptadors (nous/actualitzats/sense canvis/total API), log d'errors estructurat i detalls per expedient.
- Regles d'associació automàtica contracte→departament: per departament adjudicador, organisme, paraula clau a l'objecte, CPV; operadors igual/conté/comença per; prioritat i activació.

### 2.9 Cercador CPV
- Cerca manual per codi o descripció amb nivell.
- **Arbre CPV** navegable (lazy-load per nivells).
- **Suggeriments amb IA**: donat l'objecte del contracte, pipeline híbrid (neteja del text → detecció del tipus de contracte → extracció de paraules clau amb LLM → recuperació lèxica ponderada sobre el diccionari local amb stemming català i sinònims → re-rànquing LLM) que retorna fins a 5 codis amb probabilitat i justificació en català.

### 2.10 SuperBuscador (registre públic de tot Catalunya)
- Cerca al dataset obert de contractació de tota Catalunya (sense filtre d'organisme propi): text global, organisme, paraules clau, rang d'imports, rang de dates de publicació. Estat a la URL; resultats en targetes paginades.
- Detall extern només-lectura amb **explorador de fases** (previ, licitació, avaluació, adjudicació, formalització, anul·lació...): extracció recursiva de documents descarregables i membres de mesa des dels JSON de fase.
- Des de qualsevol document: descàrrega o **enviar al cartipàs** del generador documental.

### 2.11 Favorits
- Carpetes personals (nom, descripció, color) per organitzar expedients del SuperBuscador.
- Afegir per `codi_expedient`: es desa un **snapshot** de la font oberta dins del mateix mòdul de favorits. 🔄 Canvi v2 (2026-08-14): els expedients externs **mai** s'insereixen a les taules municipals (`contracts`), ni amb `origen='extern'` — distorsionarien la informació de l'ens. Serveixen de guia per a licitacions pròpies i, més endavant, de referència per als agents redactors (§2.14).
- Vista mestre-detall i eliminació.

### 2.12 Auditoria de contractació (red flags)
- **Possibles fraccionaments**: adjudicataris amb ≥2 contractes menors i suma ≥15.000 € el darrer any.
- **Baixes temeràries**: adjudicació ≤ 80% del preu de licitació, amb % de baixa.
- **Renovacions crítiques**: contractes en execució amb fi < 6 mesos.
- ~~Falta de concurrència~~ (endpoint present però no implementat a la v1) → 🔁 implementar a la v2 (contractes amb 1 sol licitador via `total_ofertes_rebudes`).
- **Assistent d'auditoria amb IA**: anàlisi dels red flags amb prompt personalitzable, informe executiu en Markdown.

### 2.13 Pla anual de contractació
- Entrades per exercici i trimestre: objecte, tipus, àmbit responsable, subvencionat, import estimat, departament, observacions, vinculació opcional a un expedient real (amb cercador).
- Workflow d'aprovació: no-admins creen en estat `pendent`; admins aproven.
- Secció "contractes que caduquen" per trimestre, derivada dels contractes reals (exclou obres i externs; usa la finestra d'avís per contracte o la global).
- Selector d'any (−1 a +3).

### 2.14 Generador documental amb IA (PPT/PPA/Informe)
- **Cartipàs global** (carret de documents de referència) alimentat des del detall de contracte o del SuperBuscador; persistent entre navegacions.
- Projectes de generació; cada projecte té 3 documents: **PPT** (plec de prescripcions tècniques), **PPA** (plec administratiu), **INFORME** (justificació).
- Flux: assignar referències al document → **generar índex** amb IA a partir dels PDFs de referència (extracció de text amb PyMuPDF) → per secció: instruccions pròpies + **redactar amb IA** (Markdown) → edició manual amb previsualització → desar esborrany → **exportar a Word**.
- 🔁 Deficiència v1 a corregir: la generació de secció no usa realment els documents de referència (RAG absent) i l'export Word és un HTML disfressat generat al client. La v2 ha de fer RAG real sobre les referències i export server-side (docx real).

### 2.15 Revisions de venciment
- Dues cues: "possiblement finalitzats" (data de fi passada) i "pròxims a finalitzar" (dins la finestra d'avís).
- Accions: finalitzar (canvia `estat_actual`) o descartar l'alerta, amb confirmació.
- Recàlcul d'alertes: a cada sincronització, en editar dates i en canviar la configuració de mesos; transició d'alerta genera notificació per email (a la v1 és un mock → 🔁 v2: enviament real via connector SMTP).

### 2.16 Departaments i empleats
- CRUD de departaments (codi únic, nom, descripció, actiu/inactiu — soft delete) amb vista dels seus empleats i contractes.
- **Mapeig departament ↔ grup de Gestiona** (cercador de grups via API de Gestiona, mapeig ràpid massiu).
- CRUD d'empleats (admin): nom, email, departaments múltiples, rol, contrasenya, actiu, permisos especials; soft delete i reactivació.
- Pestanya de configuració LDAP/AD: servidor, port, base DN, sufix de domini, activació i **regles de mapeig grup AD → rol + departament**.

### 2.17 Configuració (admin)
- General: codi INE10, endpoints de les fonts de dades, mesos de finestra de caducitat.
- **Mòduls activables**: pla de contractació, generador IA, auditoria IA, revisions, superbuscador, cercador CPV (el menú s'adapta).
- **Serveis IA**: interruptor mestre; proveïdor (Ollama local / Gemini); per Ollama: URL, model per tasca (CPV, auditoria), nivell de raonament; per Gemini: API key i model; **editor dels prompts** de sistema (extracció CPV, rànquing CPV, auditoria).
- **Integracions**: activació Gestiona, URL del webhook (n8n), pool URL, addon token, configuració JSON d'endpoints.
- Sincronització programada (vegeu §2.8).

### 2.18 Crèdits
- Pàgina estàtica informativa (Ajuntament de Cunit, stack tecnològic).

### 2.19 Tasques i recordatoris de contracte 🆕 (nou a la v2)
Mòdul de seguiment operatiu dins la gestió de contractes: els responsables **calendaritzen tasques i accions** sobre els seus expedients i el sistema envia recordatoris.

- **Tasca**: títol, descripció, tipus (revisió, tramitar pròrroga, tramitar liquidació, retornar garantia, informe de seguiment, reunió, altra acció), data de venciment (i hora opcional), prioritat, contracte o contracte menor associat (opcional: també entrada del pla), assignada a un o més usuaris o a un departament, estat (`pendent | en curs | feta | cancel·lada`), notes de resolució.
- **Recurrència** opcional (mensual, trimestral, anual — p. ex. "informe de seguiment trimestral" durant la vigència del contracte): en completar-se, es genera la següent ocurrència.
- **Recordatoris configurables per tasca**: N avisos (p. ex. 30, 7 i 1 dia abans) per canal — email i/o webhook (n8n → Teams/Telegram) — als assignats; re-avís diari si la tasca queda vençuda, fins a fer-la o cancel·lar-la.
- **Vistes**: calendari mensual/setmanal global i per departament; "Les meves tasques" (llista per venciment); pestanya de tasques a la fitxa de cada contracte; widget de properes tasques al dashboard; exportació **iCal** (subscripció des d'Outlook municipal).
- **Integració amb les alertes existents**: quan un contracte entra en finestra de venciment o té pròrroga possible, el sistema pot **proposar automàticament** la tasca corresponent ("tramitar pròrroga abans de {data}") perquè el responsable l'accepti i la planifiqui — les alertes passives de la v1 esdevenen accionables.
- **Permisos**: creen i gestionen tasques els responsables/gestors dels departaments del contracte (i admins); els assignats poden canviar-ne l'estat; tot canvi queda a l'historial de la tasca.

### 2.20 Assistent legal i compliment normatiu 🆕 (nou a la v2)
- **Revisió legal d'expedients**: comprovació d'un contracte (o d'un menor, o d'una entrada del pla) contra la normativa de contractació — llindars del contracte menor, durada, procediment adequat a l'import, terminis de publicitat, garanties, límits de modificació — amb informe de semàfor per comprovació i **referència a l'article concret**.
- **Revisió de documents**: checklist de conformitat sobre els plecs generats o pujats (contingut mínim, clàusules obligatòries) abans d'exportar-los.
- **Integració amb el BOE**: el sistema manté les normes subscrites (LCSP i relacionades) en versió consolidada, es vigila diàriament si canvien i, si ho fan, es re-indexen i s'avisa els administradors. Les regles internes afectades queden marcades per a revisió.
- **Garanties d'ús**: els resultats són suport a la revisió (no substitueixen l'informe jurídic preceptiu), sempre amb citació de font i acceptació humana; detall a [07-agents-ia.md](07-agents-ia.md) §2.4.

## 3. Regles de negoci crítiques (a preservar literalment)

1. **Clau natural de contracte**: (`codi_expedient`, `estat_actual`, `lots`). Un expedient pot tenir múltiples registres (un per estat i lot); els llistats mostren un representant per expedient.
2. **Detecció de canvis**: hash del registre complet de la font; si difereix → update camp a camp + historial `sincronizacion`.
3. **Origen**: `local` (ens propi) vs `extern` (fitxes del SuperBuscador). 🔄 Canvi v2: els externs viuen només com a snapshot al mòdul de favorits; les taules operatives no tenen mai files externes (l'exclusió de llistats/estadístiques/alertes/pla passa a ser estructural).
4. **Càlcul de dates**: `durada_contracte` es parseja de text ("X anys Y mesos Z dies" → mesos; >15 dies arrodoneix a +1 mes); `data_inici = data_formalitzacio + 1 dia`; `data_final = data_formalitzacio + durada + 1 dia`; la data de fi es sobreescriu amb `data_fi_prorroga` (pròrrogues) o `data_fi_execucio` (enriquiment).
5. **Alertes**: `possiblement_finalitzat` si `data_final < avui`; `alerta_finalitzacio` si `avui ≤ data_final ≤ avui + finestra`, on finestra = `meses_aviso_vencimiento` del contracte o el global `dashboard_mesos_caducitat` (def. 3–6 mesos).
6. **Associació automàtica**: primer herència de departaments d'altres registres del mateix expedient; si no, regles per prioritat; si cap aplica, queda sense assignar per a revisió manual.
7. **Fusió de duplicats**: guanya el registre amb `data_actualitzacio` més recent; el perdedor queda `rechazado`. Un duplicat validat no es pot revalidar.
8. **Fusió d'adjudicataris**: crea àlies permanent i renombra tots els contractes existents; l'àlies s'aplica a totes les sincronitzacions futures.
9. **Mapeig Socrata → model**: transcrit íntegrament a [annexos/A1-mapeig-socrata.md](annexos/A1-mapeig-socrata.md) — és l'especificació del connector, inclosos els càlculs de dates i el parsing de durada.
10. **Llindars d'auditoria**: fraccionament 15.000 €/any per adjudicatari; baixa temerària 20%; renovació crítica 6 mesos.

## 4. Defectes coneguts de la v1 (no reproduir)

Funcionals: comportament divergent entre sync bloquejant i sync stream (herència de departaments vs detecció de duplicats); recàlcul d'alertes O(n²) dins del bucle de pròrrogues; `te_prorroga` inexistent al model (export CSV trenca); referències a `departamento_id` singular eliminat (pla de contractació trenca per a no-admins); endpoint de falta de concurrència buit; emails mock.

Frontend: `useAuth` mort i cap listener de sessió expirada; `getMe()` duplicat a ~10 pàgines; recàrrega completa en canviar de vista; 7 crides seqüencials de configuració al menú; sense ruta 404; mode fosc inoperant; doble ordenació client+servidor; paginació sense total.

De seguretat: vegeu [06-seguretat.md](06-seguretat.md) §2 (llista completa de debilitats detectades a la v1 i la seva correcció per disseny).
