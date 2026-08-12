# Migració de dades v1 → v2, versió 1 (Estat: implementada)

## Context i objectiu

F1-8 del roadmap ([09-roadmap.md](../docs/09-roadmap.md); pla de dades a [04-model-de-dades.md](../docs/04-model-de-dades.md) §10): script **reproduïble i idempotent** que llegeix la base de dades de la v1 i porta a la v2 tot allò que les sincronitzacions no poden recuperar de les fonts públiques, amb informe de reconciliació. Es podrà executar tantes vegades com calgui (assajos setmanals contra còpia de producció abans del tall).

> ⚠️ **Assumpció explícita**: no hi ha hagut accés a cap còpia de la v1 durant el desenvolupament. Els noms de taules i columnes de la v1 s'han transcrit de [02-especificacio-funcional.md](../docs/02-especificacio-funcional.md) i viuen en **un únic mòdul** (`app/migration/source_map.py`): el primer assaig amb una còpia real ha de validar-los i, si cal, només es toca aquell fitxer. Els tests proven la lògica contra un esquema v1 sintètic construït des del mateix mapa.

## Comportament

- **CLI offline** (mai un endpoint): `python -m app.migration --source-dsn postgresql://… [--dry-run] [--report DIR]`. Llegeix la v1 **només en lectura**; escriu a la v2 configurada per entorn. `--dry-run` fa tot el càlcul i l'informe sense escriure (rollback final).
- **Ordre i regles** (04 §10):
  1. **departments**: alta per nom (la clau de conciliació és el nom normalitzat); si no existeix codi a la v1, se'n genera un d'estable (slug). Els existents no es dupliquen.
  2. **users**: conciliació per email (citext); mapatge de rols `admin→admin`, `responsable_contratacion→procurement_manager`, `responsable→dept_manager`, `empleado→employee`; flags `permiso_auditoria→can_audit`, `permiso_pla_contractacio→can_plan`; el DNI es **xifra** (`dni_encrypted`, AES-256-GCM); `password_hash` NO es migra (v1 usava un altre KDF: els usuaris locals hauran de restablir contrasenya; anotat a l'informe). M2M usuari↔departament.
  3. **contractors**: la v1 duplicava nom/NIF a cada fila de contracte — es dedueixen d'allà. Conciliació per `tax_id`: si ja existeix (creat pels syncs), les variants de nom es registren com a `contractor_aliases`; si no, es crea amb el nom més freqüent com a canònic.
  4. **contracts**: conciliació per **clau natural** (`file_code`,`status`,`lot`). Si el contracte ja existeix a la v2 (sincronitzat), NOMÉS es copien els camps de gestió local: `internal_status`, `warning_months_override`, departaments (M2M) i responsables (per email). Si no existeix, s'insereix sencer amb `source=local`. Mai es trepitgen camps que venen de les fonts públiques.
  5. **minor_contracts**: conciliació per `file_code`; només `internal_status` i departaments.
- **Idempotència**: re-executar no duplica res (tot són upserts per clau de conciliació) i actualitza els camps de gestió local a l'últim valor de la v1.
- **Informe de reconciliació** (`--report`, per defecte `./migration-report/`): JSON + Markdown amb, per entitat: llegits de la v1, creats, actualitzats, ja iguals, **no conciliats** (amb la llista de claus òrfenes: contractes v1 sense parella v2, responsables amb email inexistent…), i sumes de control (∑ imports adjudicació v1 vs v2 dels conciliats).
- Registre a `audit_log` (`migration.run`, actor `system`) amb el resum al final d'una execució real (no en dry-run).

## Fora d'abast (versió 1 del script; anotat a l'informe com a «pendent»)

- `settings` (re-xifrat de secrets), pla anual/carpetes/projectes documentals, `historial_contratos` i `sincronizaciones` com a llegats — arriben amb les fases 2–3, quan existeixin les taules de destí corresponents.

## Canvis d'API

Cap (eina de línia d'ordres).

## Canvis de dades

Cap migració d'esquema.

## Seguretat i permisos

- El DSN d'origen no es persisteix ni s'escriu a cap log (només l'amfitrió, sense credencials, a l'informe).
- DNI xifrat en escriure; mai en clar a l'informe ni als logs.
- La v1 s'obre en transacció de només lectura.

## Criteris d'acceptació

- [x] Migració completa contra un esquema v1 sintètic: departaments, usuaris (rols mapats, DNI xifrat), contractors dedupats amb àlies, contractes conciliats per clau natural (camps locals copiats, camps de font intactes) i v1-only inserits com a `local`.
- [x] Re-run: cap duplicat, comptadors `unchanged`.
- [x] `--dry-run` no escriu res.
- [x] Informe amb comptatges, òrfenes i sumes de control.
- [x] Bateries verdes.
