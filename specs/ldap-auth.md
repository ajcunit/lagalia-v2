# Autenticació LDAP/Active Directory (Estat: implementada)

## Context i objectiu

F2 del roadmap i 02 §login: iniciar sessió amb el compte corporatiu de
l'Ajuntament (AD) a més del login local. Reescriptura endurida del connector
v1 (08 §2.4): filtres sempre escapats (la v1 era injectable), LDAPS/StartTLS
obligatori, timeout curt i, si l'AD cau, **el login local continua**.

## Comportament

### Connector `ldap` (hub)

- Config (no secreta): `server_url` (host o `ldaps://…`/`ldap://…`),
  `port` (per defecte 636; el de la URL mana), `base_dn`, `domain_suffix`
  (`@ajuntament.local`, com a la v1), `starttls` (bool), `timeout_seconds`
  (per defecte 5). Credencials (write-only, **opcionals**): `bind_dn`,
  `bind_password` (compte de servei).
- **Transport segur obligatori**: sense esquema s'assumeix LDAPS;
  `ldap://` només s'accepta amb `starttls` (mai bind en clar).
- Autenticació amb ldap3 (en thread, l'API no es bloqueja), cerca sempre
  per `(|(sAMAccountName=X)(mail=X)(userPrincipalName=X))` amb el valor
  **escapat RFC 4515** (`escape_filter_chars`) i atributs mínims
  (displayName, mail, sAMAccountName, memberOf):
  - **Amb compte de servei**: bind de servei → cerca → bind de verificació
    amb el DN trobat i la contrasenya de l'usuari.
  - **Sense compte de servei** (paritat v1): bind directe com a usuari
    (UPN = login + `domain_suffix` si no porta `@`) i cerca de la pròpia
    entrada per obtenir els grups.
- Healthcheck: bind de servei + cerca base (sense compte de servei només
  valida transport: la connexió real es prova al primer login).
- El «grup d'accés obligatori» de la v1 el substitueixen les regles de rol:
  sense grup de rol casat, ningú no entra.

### Mapatge grup AD → rol + departament (migració 0032)

Model organitzatiu de l'Ajuntament: cada usuari LDAP té **un grup per tipus
de rol** (és el que dona accés a la plataforma i fixa el rol) i, a banda,
**un grup que assigna el departament**. Per això cada regla és d'un tipus:

- Taula `ldap_group_mappings`: `ad_group` (DN sencer o CN, case-insensitive,
  UNIQUE), `role` (enum de rols, nullable), `department_id` (FK, nullable),
  amb CHECK que exactament un dels dos és present: una regla o bé és **de
  rol** (grup → rol) o bé **de departament** (grup → departament).
- Resolució: es casen els `memberOf` de l'usuari contra les regles (DN
  complet o CN); el **rol més alt** de les regles de rol casades guanya
  (admin > gestió > responsable > consulta); els departaments són la unió
  de les regles de departament casades i substitueixen els assignats
  (sincronització a cada login).
- **Sense cap regla de rol casada → accés denegat**: el grup de rol és el
  que dona entrada a la plataforma; l'AD autentica, però només entren els
  membres dels grups donats d'alta.

### Flux de login (users/service.login)

1. Usuari local amb `password_hash` → verificació local (els admins locals
   mai depenen de l'AD).
2. Sense usuari local o usuari amb `password_hash NULL` (LDAP) → intent LDAP
   si el connector està habilitat: autenticació + **provisió automàtica**
   (crea o actualitza nom, correu, rol i departaments; `password_hash` NULL).
3. AD caigut o timeout → l'intent LDAP falla en silenci (auditat) i el flux
   local queda intacte: credencials incorrectes per a l'usuari LDAP, login
   normal per als locals.
- Auditoria: `auth.login` amb èxit/fracàs com fins ara + `auth.ldap_provision`
  quan es crea/actualitza un usuari des de l'AD.

### API i pantalla

- `GET/POST /ldap/group-mappings` i `DELETE /ldap/group-mappings/{id}`
  (lectura `config:read`, escriptura `config:write`; tag `config`).
- **Paràmetres i connectors** (/admin/config) passa a pestanyes:
  Paràmetres · Connectors · **LDAP**. La pestanya LDAP ho té tot en un
  lloc: la targeta del connector `ldap` (servidor, base DN, StartTLS,
  compte de servei write-only, activació i healthcheck) i, a sota, la
  taula de regles de mapatge (grup AD → rol o departament) amb alta i
  baixa. El connector també surt a la pestanya Connectors, com la resta.

## Canvis d'API

Els tres endpoints de mapatges (openapi.yaml + client TS regenerat). El
login no canvia de contracte.

## Seguretat

- Filtres LDAP sempre escapats (RFC 4515); cap valor d'usuari concatenat.
- Bind de servei amb credencials write-only del hub; TLS verificat.
- La contrasenya de l'usuari només s'usa per al bind de verificació; mai es
  desa ni s'enregistra.
- Timeout de 5s i captura d'errors: l'AD caigut no tomba el login local.

## Fora d'abast

- Sincronització programada d'altes/baixes (desactivar usuaris fora del
  grup) — anotada al backlog; SSO/Kerberos; grups imbricats (memberOf només
  directe).

## Criteris d'acceptació

- [x] Login LDAP amb provisió automàtica (rol més alt + unió de departaments).
- [x] Filtre escapat (test amb valors maliciosos); LDAPS/StartTLS obligatori.
- [x] AD caigut → login local intacte; usuari sense mapatge → denegat.
- [x] Pestanya LDAP amb CRUD de mapatges; bateries verdes.
