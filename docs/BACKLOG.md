# BACKLOG — LAGALia v2

Registre únic de tot allò que sorgeix durant el desenvolupament: idees, deute tècnic, desviacions de spec, peticions d'usuari i troballes. Funcionament i cicle de vida: [11-metodologia-specs.md](11-metodologia-specs.md) §3.

**Prioritats:** `P1` bloqueja la fase en curs · `P2` propera fase · `P3` millora quan es pugui.
**Estats:** `Proposta → Triada → Especificada → En curs → Feta` (o `Descartada`).

**Norma:** res no s'implementa des de `Proposta`. En passar a `Especificada` s'actualitzen les specs mestres afectades; en tancar-se, l'entrada enllaça la PR.

---

## Obertes

### B-001 · Mitigar debilitats crítiques de seguretat a la v1 mentre conviu amb la v2
- **Prioritat:** P1 · **Estat:** Proposta · **Mida:** S
- **Descripció:** la v1 continuarà en producció durant tot el projecte (~4 mesos). Dues debilitats permeten a qualsevol usuari autenticat robar secrets: `GET /api/config/` retorna API keys i tokens, i `/api/empleados/` exposa els tokens de Gestiona d'altres usuaris.
- **Com desenvolupar-la:** pegat mínim sobre la v1 — filtrar claus secretes a la resposta de config i eliminar els camps de token del schema d'empleat. No refactoritzar res més: la v1 està congelada funcionalment.
- **Specs afectades:** cap de la v2 (és manteniment de la v1); anotar el resultat a [06-seguretat.md](06-seguretat.md) §2 files 1-2.

### B-002 · Contracte real del webhook Gestiona sense el token d'usuari al cos
- **Prioritat:** P1 · **Estat:** Proposta · **Mida:** M
- **Descripció:** la v2 elimina l'enviament del `gestiona_access_token` personal dins del payload cap a n8n ([06-seguretat.md](06-seguretat.md) §2 fila 9), però cal validar amb l'entorn de proves de Gestiona quina alternativa funciona (credencial pròpia de n8n o token efímer d'abast mínim).
- **Com desenvolupar-la:** provar contra l'entorn de proves abans de la Fase 2; documentar el contracte definitiu a [08-hub-integracions.md](08-hub-integracions.md) §2.3 i escriure'n la spec de feature amb els contract tests que farà servir també el mode `n8n_bridge`.

### B-003 · Decidir emmagatzematge d'objectes: sistema de fitxers o MinIO
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** S
- **Descripció:** [03-arquitectura.md](03-arquitectura.md) §2.6 deixa obert si els documents descarregats i generats van a disc muntat o a MinIO (S3).
- **Com desenvolupar-la:** decidir segons la infraestructura municipal disponible i la política de còpies; l'abstracció d'emmagatzematge s'ha d'escriure igualment perquè el canvi sigui de configuració.

### B-004 · Dataset d'or per avaluar el classificador CPV
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** M
- **Descripció:** [07-agents-ia.md](07-agents-ia.md) §5 preveu mesurar el pipeline CPV amb parells objecte→codi validats, però el dataset inicial no existeix.
- **Com desenvolupar-la:** extreure'l dels contractes històrics ja classificats de la v1 (mostra revisada manualment), i alimentar-lo després amb el feedback loop de la pròpia aplicació.

### B-005 · Abast del corpus normatiu inicial de l'assistent legal
- **Prioritat:** P2 · **Estat:** Proposta · **Mida:** S
- **Descripció:** cal fixar quines normes se subscriuen al connector BOE el dia 1 (LCSP i quines altres) i si s'inclou normativa autonòmica (DOGC) i instruccions internes de contractació.
- **Com desenvolupar-la:** llista acordada amb Secretaria/Intervenció; documentar-la a [07-agents-ia.md](07-agents-ia.md) §3bis i carregar-la com a dades inicials del connector.

### B-006 · Política de retenció i purga de dades
- **Prioritat:** P3 · **Estat:** Proposta · **Mida:** S
- **Descripció:** [06-seguretat.md](06-seguretat.md) §7 fixa 2 anys d'auditoria i 1 any per a entrades/sortides d'IA com a valors per defecte, però han de ser validats per la responsable de protecció de dades de l'ajuntament.
- **Com desenvolupar-la:** validació formal, i implementar la purga com a job programat configurable.

---

## Tancades

*(cap encara)*

---

## Descartades

*(cap encara)*
