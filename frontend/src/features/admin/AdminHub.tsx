import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { ADMIN_TILES, visibleItems } from "../../components/navigation";
import { EmptyState } from "../../components/ui";
import { t } from "../../i18n";

/** Hub de configuració (B-015): totes les pantalles d'administració en un lloc. */
export function AdminHub() {
  const { permissions } = useAuth();
  const tiles = visibleItems(ADMIN_TILES, permissions?.actions ?? []);

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight text-ink">{t("adminHub.title")}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("adminHub.intro")}</p>

      {tiles.length === 0 ? (
        <div className="mt-6">
          <EmptyState icon="🔒" title={t("adminHub.empty")} />
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {tiles.map((tile) => (
            <Link
              key={tile.to}
              to={tile.to}
              className="group flex items-start gap-4 rounded-2xl border border-line bg-surface-raised p-5 shadow-card transition-colors hover:border-accent/50 hover:bg-accent-soft/40"
            >
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
                <tile.icon aria-hidden className="h-6 w-6" strokeWidth={1.8} />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold text-ink group-hover:text-accent">
                  {t(tile.labelKey)}
                </span>
                <span className="mt-1 block text-sm text-muted">{t(tile.descriptionKey)}</span>
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
