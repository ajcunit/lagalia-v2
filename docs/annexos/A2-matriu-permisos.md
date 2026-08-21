# Annex A2 — Matriu de permisos

Transcripció de la matriu real implementada a la v1 (extreta dels checks dispersos pels 15 routers) i **matriu objectiu de la v2**. A la v2 aquesta taula és la font de la implementació del motor d'autorització i del test parametritzat (rol × acció × abast) exigit a [06-seguretat.md](../06-seguretat.md) §3.

## 1. Rols

| v1 | v2 (anglès) | Descripció |
|---|---|---|
| `admin` | `admin` | Accés total |
| `responsable_contratacion` | `procurement_manager` | Gestió de contractació sense administració del sistema |
| `responsable` | `dept_manager` | Responsable de departament / de contractes concrets |
| `empleado` | `employee` | Consulta |

Flags independents del rol: `permiso_auditoria` → `can_audit`; `permiso_pla_contractacio` → `can_plan`.

## 2. Matriu (✔ permès · ✔ᴰ només dins el seu abast departamental · — denegat)

| Acció | admin | procurement_manager | dept_manager | employee |
|---|---|---|---|---|
| **Contractes** |
| Llistar / veure detall | ✔ | ✔ | ✔ᴰ | ✔ᴰ |
| Crear manualment | ✔ | ✔ | — | — |
| Editar camps generals | ✔ | ✔ | — | — |
| Editar `warning_months_override` | ✔ | ✔ | ✔ᴰ | — |
| Assignar departaments / responsables | ✔ | ✔ | — | — |
| Assignació massiva | ✔ | ✔ | — | — |
| Finalitzar / descartar alerta | ✔ | ✔ | ✔ (si n'és responsable) | — |
| Enriquir (individual o batch) | ✔ | ✔ | — | — |
| Exportar CSV/XLSX | ✔ | ✔ | ✔ᴰ | ✔ᴰ |
| Obrir a Gestiona | ✔ | ✔ | — | — |
| **Menors** |
| Llistar / veure | ✔ | ✔ | ✔ᴰ | ✔ᴰ |
| Editar / assignar departaments | ✔ | ✔ | — | — |
| **Duplicats** |
| Veure i validar (contractes i adjudicataris) | ✔ | ✔ | — | — |
| **Sincronització** |
| Executar qualsevol sync / veure historial | ✔ | ✔ | — | — |
| Gestionar regles d'associació | ✔ | ✔ | — | — |
| **Organització** |
| CRUD departaments | ✔ | ✔ | — | — |
| CRUD usuaris | ✔ | — ⚠️ | — | — |
| Editar perfil propi | ✔ | ✔ | ✔ | ✔ |
| **Configuració** |
| Llegir configuració no secreta | ✔ | ✔ | ✔ | ✔ |
| Escriure configuració / secrets / connectors / IA | ✔ | — | — | — |
| **Pla anual** |
| Veure | ✔ | ✔ | ✔ᴰ (o `can_plan`) | ✔ᴰ (si `can_plan`) |
| Crear/editar (queda `pendent` si no és admin) | ✔ | ✔ | ✔ᴰ si `can_plan` | ✔ᴰ si `can_plan` |
| Aprovar entrades | ✔ | — | — | — |
| **Auditoria de contractació** |
| Red flags i assistent IA | ✔ | ✔ si `can_audit` | ✔ si `can_audit` | ✔ si `can_audit` |
| **Auditoria de seguretat** (nova v2) |
| Consultar `audit_log` | ✔ | — | — | — |
| **Sistema** (nou v2) |
| Estat del sistema, readiness i ús de la plataforma (`system:read`) | ✔ | — | — | — |
| **Processos BPM** (nou v2, mòdul activable) |
| Veure processos i instàncies (`bpm:read`) | ✔ | ✔ | — | — |
| Gestionar processos i instàncies (`bpm:manage`) | ✔ | ✔ | — | — |
| **Tasques** (nou v2) |
| Veure | ✔ | ✔ | ✔ᴰ | ✔ᴰ (assignades) |
| Crear/editar sobre contractes del seu àmbit | ✔ | ✔ | ✔ᴰ | — |
| Canviar estat d'una tasca assignada | ✔ | ✔ | ✔ | ✔ |
| **Revisió legal** (nova v2) |
| Executar revisió | ✔ | ✔ | ✔ᴰ | — |
| Editar regles de compliment / normes BOE | ✔ | — | — | — |
| **Generador documental, favorits, CPV, SuperBuscador** |
| Ús propi | ✔ | ✔ | ✔ | ✔ |

⚠️ **Divergència v1 → v2**: a la v1 el `responsable_contratacion` pot crear i editar usuaris (`empleados.py` accepta `["admin","responsable_contratacion"]`). A la v2 la gestió d'usuaris queda **només per a admin**, coherent amb la separació entre gestió de contractació i administració del sistema. Cal validar-ho amb l'organització abans d'implementar-ho (entrada de backlog si es vol mantenir el comportament v1).

## 3. Abast departamental (ᴰ)

Un usuari veu un contracte si es compleix qualsevol de:
- pertany a algun dels departaments assignats al contracte, **o**
- és a la llista de responsables del contracte.

Si l'usuari no té cap departament i el recurs no té responsables, no veu res (mai "tot").

**Mode de vista**: `admin` i `procurement_manager` poden demanar abast complet (*Vista Admin*) o restringit (*Vista Usuari*). A la v2 és un paràmetre de consulta validat contra el rol real, **no** una capçalera de confiança com a la v1 (`X-View-Mode`).

## 4. Regles crítiques que la implementació ha de respectar

1. **L'abast s'aplica també als detalls i subrecursos**, no només als llistats (l'IDOR és el defecte més greu de la v1: `/contratos/{id}`, historial, pròrrogues, modificacions i menors no filtraven).
2. **Cap check de rol als routers**: una única dependency `Authorize(action)` + resource loader.
3. Els scopes d'API (service accounts i agents d'IA) es mapegen sobre les mateixes accions d'aquesta taula; un agent mai supera l'abast del seu compte.
4. Tota denegació es registra a `audit_log` amb actor, acció i recurs.
