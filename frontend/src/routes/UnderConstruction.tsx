import { t } from "../i18n";

/** Estat buit per a pantalles de fases futures (10-ui.md §5). */
export function UnderConstruction() {
  return (
    <div className="mx-auto max-w-md py-24 text-center">
      <p aria-hidden="true" className="text-4xl">
        🚧
      </p>
      <h1 className="mt-4 text-xl font-semibold text-ink">
        {t("common.underConstruction")}
      </h1>
      <p className="mt-2 text-muted">{t("common.underConstructionDetail")}</p>
    </div>
  );
}
