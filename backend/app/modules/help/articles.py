"""Wiki d'ajuda integrada (specs/help-wiki.md).

Contingut estàtic i versionat amb el codi: cada canvi de funcionament
hauria de tocar l'article corresponent. `audience="admin"` = només
visible per al rol admin (pantalles de configuració).
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class HelpArticle:
    slug: str
    title: str
    audience: Literal["all", "admin"]
    body: str


ARTICLES: list[HelpArticle] = [
    HelpArticle(
        slug="primers-passos",
        title="Primers passos",
        audience="all",
        body="""## Entrar a LAGALia

Entra amb el teu **compte corporatiu** (correu i contrasenya de l'Ajuntament) —
el compte es crea sol el primer cop — o amb un compte local si en tens un.

## Orientar-se

- **Menú lateral**: les pantalles a què tens accés segons el teu rol. La roda
  dentada de baix (només administradors) porta a la configuració.
- **Barra superior**: a l'esquerra, el **selector de vista** — tria si veus les
  dades d'un departament concret, de tots els teus, o de tot l'ens (segons
  permisos). A la dreta, els **avisos**: tasques obertes i vençudes, contractes
  a punt de vèncer i pendents de revisió. Cada xip és clicable.
- **El teu nom** (baix del menú): desplegable amb el mode fosc i tancar sessió.

## D'on surten les dades

Els contractes es sincronitzen automàticament cada nit des de les fonts
públiques (PSCP, registre públic de contractes, dades obertes). No cal
introduir-los a mà: la plataforma els manté al dia.""",
    ),
    HelpArticle(
        slug="contractes",
        title="Contractes",
        audience="all",
        body="""## Llistat

Cerca per text, filtra per estat, tipus, anys, departament, venciments o
sense departament assignat. Els filtres booleans són interruptors. Les
columnes es poden exportar (CSV/Excel) amb els filtres aplicats.

## Fitxa de l'expedient

Pestanyes: **Resum** (dades, cronologia, CPV), **Documents** (per fases, amb
carpetes; envia'ls a un projecte del generador o demana'n la revisió legal),
**Execució** (pròrrogues, modificacions, actuacions publicades), **Adjudicatari**,
**Historial** (tot canvi queda registrat), **Tasques** i **Xat** (pregunta sobre
l'expedient o sobre un document concret).

## Esmenar dades mal informades

Si una dada ve malament de la font (una data, un import), un gestor pot
**editar-la** («Edita les dades» al Resum). Cada camp esmenat queda **protegit**:
la sincronització nocturna ja no el trepitjarà. Tot queda a l'historial.

## Avisos de venciment

L'avís global és configurable; a més, cada expedient pot tenir el seu propi
termini d'avís (camp «avís de venciment» a l'edició; buit = valor global).""",
    ),
    HelpArticle(
        slug="contractes-menors",
        title="Contractes menors",
        audience="all",
        body="""Els menors se sincronitzen del registre públic (procediment «Menor») i tenen
llistat i fitxa propis, més lleugers que els majors.

- **Assignació a departaments**: manual des de la fitxa o per regles
  d'associació; el filtre «sense departament» ajuda a repartir la feina.
- **Estat intern**: normal, pendent de revisió, aprovat o rebutjat — útil per
  al circuit de revisió de menors.
- El **llindar dels 15.000 €** (LCSP) es vigila des de l'auditoria de riscos:
  fraccionaments i acumulacions per adjudicatari surten com a red flags.""",
    ),
    HelpArticle(
        slug="adjudicataris",
        title="Adjudicataris",
        audience="all",
        body="""## Fitxa

Pestanyes: **Resum** (volums i contractes vinculats), **Contacte** (telèfon,
correu, tipus d'empresa — s'omplen sols des dels expedients publicats) i
**Anàlisi de mercat**.

## Anàlisi de mercat

Consulta en viu les dades obertes de tota Catalunya: amb quines
administracions ha treballat l'adjudicatari, quants expedients, imports
formalitzats i mitjanes. Cada organisme es pot desplegar per veure els
contractes concrets i obrir-ne la fitxa externa.

## Duplicats

La font pública escriu el mateix NIF amb variants de nom. La plataforma els
normalitza a la ingesta i agrupa els dubtosos per NIF a la pantalla de
**Duplicats** (administració): tries el nom canònic i fusiones el grup, o el
rebutges si són empreses diferents legítimes. L'històric de fusions i
rebutjos es conserva sempre.""",
    ),
    HelpArticle(
        slug="tasques",
        title="Tasques i calendari",
        audience="all",
        body="""Tasques vinculades (o no) a expedients: revisions, pròrrogues, liquidacions,
retorns de garantia, reunions…

- **Assignació** a una o més persones; les teves tasques obertes i vençudes
  surten a la barra superior.
- **Recordatoris** per correu amb antelacions configurables, i re-avís de les
  vençudes.
- **Feed iCal** per subscriure el calendari corporatiu (Outlook, etc.).
- Les **alertes de venciment** de contractes poden proposar tasques
  automàticament; sempre les confirma una persona.""",
    ),
    HelpArticle(
        slug="superbuscador-favorits",
        title="SuperBuscador i favorits",
        audience="all",
        body="""## SuperBuscador

Cerca a **tota la contractació pública de Catalunya** (dades obertes), no
només la del nostre ens: per text, organisme, tipus, anys, NIF
d'adjudicatari… Cada resultat obre una **fitxa externa** amb pestanyes
(resum, documents per fases, lots) sense sortir de LAGALia.

## Favorits

Desa expedients externs a **carpetes** («⭐ Desa», amb creació de carpeta al
vol). Els favorits guarden una còpia de les dades del moment — no toquen les
taules municipals. Des d'un favorit o una fitxa externa pots enviar
documents directament a un **projecte del generador documental**
(«＋ projecte»).""",
    ),
    HelpArticle(
        slug="generador-documental",
        title="Generador documental",
        audience="all",
        body="""Redacta documents de contractació (plecs, informes) amb l'ajuda de la IA i
amb **referències reals**.

1. Crea un **projecte** i afegeix-hi referències: documents d'expedients
   propis, del SuperBuscador o **PDF pujats del teu ordinador**. S'indexen
   temporalment (només dins del projecte, amb caducitat i purga).
2. **Genera l'índex** amb IA a partir de les referències, o comença'l a mà.
3. Per secció: escriu-la tu o **redacta-la amb IA** (amb les referències com a
   context); després la pots **millorar amb IA** mantenint el teu text com a
   base.
4. **Exporta a Word** quan estigui llest.

La IA mai publica res sola: tot el que genera queda com a esborrany fins que
tu ho acceptes.""",
    ),
    HelpArticle(
        slug="xat-i-analista",
        title="Xat i analista de dades",
        audience="all",
        body="""*(cal permís d'anàlisi per al xat general)*

## Xat general

Conversa multi-torn sobre la contractació de l'ens: l'assistent consulta les
dades reals (contractes, adjudicataris, imports) **respectant el teu abast**
— si no veus els contractes d'un altre departament, l'assistent tampoc.
També sap respondre **com funciona la plataforma** (aquesta mateixa ajuda).

## Xat de l'expedient

A la pestanya Xat de cada contracte: l'assistent té el context d'aquell
expedient i els seus documents indexats, amb citació de la font. Pots
**limitar la pregunta a un sol document** amb el selector «Pregunta sobre».

## Revisió legal

Qualsevol document del repositori amb còpia local es pot passar per la
**revisió legal** (LCSP): assenyala riscos amb citació d'articles.""",
    ),
    HelpArticle(
        slug="auditoria-riscos",
        title="Auditoria de riscos",
        audience="all",
        body="""*(cal permís d'auditoria)*

Els **red flags** es recalculen sobre les dades sincronitzades: possibles
fraccionaments de menors, acumulació d'imports per adjudicatari, manca de
concurrència, venciments sense tramitar…

- Pantalla d'**Auditoria** amb els blocs de risc i el detall de cada troballa.
- **Informe executiu** generat per IA sota demanda, i **informe periòdic**
  automàtic per correu si l'administració l'activa (desactivat de sèrie).
- L'**analista** pot respondre preguntes obertes sobre aquestes dades.""",
    ),
    HelpArticle(
        slug="pla-anual",
        title="Pla anual de contractació",
        audience="all",
        body="""*(cal permís de planificació)*

Planifica les licitacions de l'exercici: objecte, tipus, import estimat,
calendari previst, subvencionat o no, i notes. El pla es pot contrastar amb
la contractació real de l'any i exportar per a la seva publicació.""",
    ),
    HelpArticle(
        slug="configuracio",
        title="Configuració de la plataforma",
        audience="admin",
        body="""*(només administradors — pantalla /admin/config)*

## Paràmetres

Taula de paràmetres coneguts, sempre visibles i editables: avís de venciment
global, destinataris d'informes, fases indexables del RAG, **retenció de
dades** (`retention.audit_log_days`, `retention.ai_days` — ajustables segons
el DPO), programació nocturna, informe d'auditoria…

## Mòduls

Cada mòdul de la plataforma (menors, adjudicataris, xat, generador…) té un
interruptor: desactivar-lo l'amaga del menú de tothom i **talla la seva API
al servidor**. Les dades no s'esborren mai. El nucli (contractes, usuaris,
configuració, auditoria) no es pot desactivar.

## Connectors

Targetes per connector (dades obertes, portal de contractació, LDAP, SMTP,
BOE): activació, configuració, credencials (només escriptura) i healthcheck.

## LDAP / Directori

Connexió amb l'Active Directory, **regles de mapatge** (grup de rol → dona
accés i rol; grup de departament → assigna departament) i el diagnòstic
«Prova un inici de sessió» que mostra pas a pas què passa i els grups reals
de l'usuari.""",
    ),
    HelpArticle(
        slug="sincronitzacions",
        title="Sincronitzacions i dades",
        audience="admin",
        body="""*(administració — pantalla /admin/sync)*

## Execucions

Llança manualment cada tipus de sincronització (contractes, menors,
extensions, execució, CPV, enriquiment) i consulta l'històric amb comptadors
i errors per element.

## Programació

La **cadena nocturna** (contractes → extensions → menors → execució) corre
cada dia a l'hora configurada (Europe/Madrid), amb dies de la setmana
triables. L'**informe d'auditoria automàtic** també es programa aquí
(desactivat de sèrie). Els canvis s'apliquen sense reiniciar res.

## Safata de jobs

Jobs morts (reintents esgotats), fallits o encuats, amb **re-encuament
manual**. Un job que falla es reintenta sol amb espera creixent abans de
donar-se per mort.

## Mapejador de camps

Si una dada ve mal mapada de la font (Socrata, registre públic, execució,
JSON del portal), es corregeix **des de la pantalla** de mapatge de camps:
tries el camp d'origen amb mostres reals i llances el remapatge local. Les
esmenes manuals d'expedients concrets sempre manen sobre el mapatge.""",
    ),
    HelpArticle(
        slug="usuaris-i-acces",
        title="Usuaris, departaments i accés",
        audience="admin",
        body="""*(administració)*

## Rols

**Admin** (tot), **responsable de contractació** (tot excepte configuració i
usuaris), **responsable de departament** (els seus departaments) i
**consulta**. Flags addicionals: auditoria i pla anual.

## Usuaris

Alta local o **provisió automàtica per LDAP** (el primer login crea l'usuari
amb rol i departaments segons els grups d'AD). Un compte local amb
contrasenya mai s'autentica contra l'AD — és la xarxa de seguretat si el
directori cau.

## Departaments

Els departaments delimiten l'abast de les dades. L'assignació d'expedients
és manual, per herència del mateix expedient o per regles d'associació.

## Integracions sortints

**Webhooks** signats (HMAC) amb reintents i safata de fallits, i **comptes de
servei** amb API keys d'abast mínim per a n8n i altres automatitzacions.

## Auditoria de seguretat

Tot queda a l'`audit_log` (encadenat amb hashos, verificable, append-only).
La retenció es purga automàticament segons els terminis del DPO.""",
    ),
]


def visible_articles(*, is_admin: bool) -> list[HelpArticle]:
    return [a for a in ARTICLES if is_admin or a.audience == "all"]


def get_article(slug: str, *, is_admin: bool) -> HelpArticle | None:
    for article in visible_articles(is_admin=is_admin):
        if article.slug == slug:
            return article
    return None
