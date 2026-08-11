# <Nom de la funcionalitat>

- **Backlog**: B-nnn
- **Estat**: proposta | aprovada | implementada
- **Fase del roadmap**: 
- **Specs mestres afectades**: <!-- p. ex. docs/02 §2.4, docs/04 §2, docs/05 -->

## Context i objectiu

Què problema resol, per a qui, i per què ara. Si substitueix comportament
existent, digues quin.

## Comportament

Regles funcionals verificables. Fes servir Given/When/Then quan aporti claredat:

```
Donat que <estat inicial>
Quan <acció>
Aleshores <resultat observable>
```

Casos límit i errors esperats inclosos: què passa amb dades absents, permisos
insuficients, concurrència o fallada d'un servei extern.

## Canvis d'API

Delta d'`openapi.yaml`: endpoints nous o modificats, esquemes, scopes requerits,
codis d'error. Si no en té, escriu "cap".

## Canvis de dades

Taules i columnes noves o modificades, índexs, i pla de migració (incloent què
passa amb les dades existents). Si no en té, escriu "cap".

## Seguretat i permisos

Qui pot fer què (referència a `docs/annexos/A2-matriu-permisos.md`), abast
departamental, què s'ha de registrar a `audit_log`, i quines entrades són no
fiables i com es validen.

## UI

Pantalles i patrons afectats (referència a `docs/10-ui.md`): què veu cada rol,
estats de càrrega, buits i error, i requisits d'accessibilitat específics.

## Fora d'abast

Què NO fa aquesta feina, per evitar que creixi durant la implementació.

## Criteris d'acceptació

- [ ] ...
- [ ] ...

Aquests criteris són la base dels tests automàtics: han de ser comprovables
sense ambigüitat.
