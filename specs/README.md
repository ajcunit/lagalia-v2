# specs/ — Especificacions de funcionalitat

Una spec per peça de treball no trivial. Concreta **com** s'implementa una cosa,
abans d'escriure codi; les specs mestres de `docs/` defineixen el **què** i el
**perquè**.

## Com s'usa

1. L'entrada neix a [`docs/BACKLOG.md`](../docs/BACKLOG.md) i es prioritza.
2. En passar a `Especificada`, es copia [`_TEMPLATE.md`](_TEMPLATE.md) a
   `<feature>.md`, s'omple i es revisa (PR només de spec).
3. S'implementa. La PR de codi actualitza aquesta spec a `implementada` i les
   specs mestres afectades.
4. Quan el contingut ja viu consolidat a les specs mestres, la spec de
   funcionalitat es queda com a registre històric de la decisió.

Nom de fitxer: `<àmbit>-<acció>.md` en anglès i minúscules, per exemple
`contracts-bulk-assign.md`, `connectors-n8n-bridge.md`, `ai-cpv-classifier.md`.

Regles completes: [`docs/11-metodologia-specs.md`](../docs/11-metodologia-specs.md).
