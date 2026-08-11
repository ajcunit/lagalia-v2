import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { t } from "../i18n";
import { NAV_ZONES, visibleZones } from "./navigation";
import { ThemeToggle } from "./ThemeToggle";

/** Shell autenticat: sidebar per permisos (una crida) + capçalera. */
export function Shell() {
  const { user, permissions, logout } = useAuth();
  const zones = visibleZones(NAV_ZONES, permissions?.actions ?? []);

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r border-line bg-surface-raised">
        <div className="px-4 py-5">
          <p className="text-lg font-bold tracking-tight text-ink">{t("app.name")}</p>
        </div>
        <nav aria-label={t("shell.navigation")} className="px-2 pb-6">
          {zones.map((zone) => (
            <div key={zone.labelKey} className="mt-4">
              <p className="px-2 text-xs font-semibold tracking-wide text-muted uppercase">
                {t(zone.labelKey)}
              </p>
              <ul className="mt-1 space-y-0.5">
                {zone.items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        `block rounded-md px-2 py-1.5 text-sm ${
                          isActive
                            ? "bg-accent-soft font-medium text-accent"
                            : "text-ink hover:bg-surface-sunken"
                        }`
                      }
                    >
                      {t(item.labelKey)}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-3 border-b border-line bg-surface-raised px-6 py-3">
          {user && (
            <p className="text-sm text-muted">
              <span className="font-medium text-ink">{user.name}</span>
              {" · "}
              {t(`role.${user.role}`)}
            </p>
          )}
          <ThemeToggle />
          <button
            type="button"
            onClick={() => void logout()}
            className="rounded-md border border-line bg-surface-raised px-3 py-2 text-sm text-ink shadow-card hover:bg-surface-sunken"
          >
            {t("shell.logout")}
          </button>
        </header>
        <main id="content" className="flex-1 px-8 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
