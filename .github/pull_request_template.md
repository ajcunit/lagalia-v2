# Què fa aquesta PR

<!-- Resum en 2-3 frases. Si ve del backlog, enllaça l'entrada: docs/BACKLOG.md B-nnn -->

Backlog: <!-- B-nnn o "cap" -->
Spec de funcionalitat: <!-- specs/<feature>.md o "cap (refactor pur)" -->

## Sincronització spec ↔ codi

> Regla del projecte: una PR que canvia comportament porta el canvi de spec a la
> mateixa PR (`docs/11-metodologia-specs.md`). Marca el que aplica; si una casella
> no aplica, escriu-hi per què.

- [ ] Specs mestres afectades actualitzades (`docs/0X-*.md`) — quines: 
- [ ] Spec de funcionalitat creada o actualitzada d'estat
- [ ] `openapi.yaml` actualitzat i client TS regenerat
- [ ] Migració Alembic coherent amb `docs/04-model-de-dades.md`
- [ ] Entrada de `docs/BACKLOG.md` actualitzada (estat i enllaç a aquesta PR)
- [ ] Cap desviació silenciosa: les desviacions estan marcades a la spec

## Seguretat

- [ ] L'autorització passa pel motor central i s'aplica també a detalls i subrecursos
- [ ] Cap secret a respostes, logs ni payloads
- [ ] Entrades externes validades (sense concatenació a consultes SQL/SoQL/LDAP)
- [ ] Les escriptures noves deixen rastre a `audit_log`

## Verificació

- [ ] Tests nous o actualitzats; suite verda en local
- [ ] Contract testing verd
- [ ] Provat manualment: <!-- com -->

## Notes per a qui revisa

<!-- Decisions discutibles, alternatives descartades, què mirar amb més atenció -->
