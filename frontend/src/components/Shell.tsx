import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { t } from "../i18n";
import { ADMIN_NAV_ITEM, canSeeAdminHub, MAIN_NAV, visibleItems } from "./navigation";
import { ThemeToggle } from "./ThemeToggle";

/** Shell autenticat (B-015 fase 1): sidebar amb icones i aire + hub d'administració. */
export function Shell() {
  const { user, permissions, logout } = useAuth();
  const actions = permissions?.actions ?? [];
  const disabledModules = permissions?.disabled_modules ?? [];
  const items = visibleItems(MAIN_NAV, actions, disabledModules);
  const showAdmin = canSeeAdminHub(actions, disabledModules);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col border-r border-line bg-surface-raised">
        <div className="px-6 pb-3 pt-5 text-center">
          <p className="text-2xl font-extrabold tracking-tight text-ink">
            LAGAL<span className="text-accent">ia</span>
          </p>
          <p className="mt-0.5 text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
            Contractació
          </p>
        </div>
        <nav aria-label={t("shell.navigation")} className="min-h-0 flex-1 px-3 pb-2">
          <ul className="space-y-0.5">
            {items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-xl px-3 py-2 text-sm ${
                      isActive
                        ? "bg-accent-soft font-semibold text-accent"
                        : "text-ink hover:bg-surface-sunken"
                    }`
                  }
                >
                  <item.icon aria-hidden className="h-5 w-5 shrink-0" strokeWidth={1.8} />
                  {t(item.labelKey)}
                </NavLink>
              </li>
            ))}
            {showAdmin && (
              <li className="pt-2">
                <div className="mx-3 mb-2 border-t border-line" />
                <NavLink
                  to={ADMIN_NAV_ITEM.to}
                  end
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-xl px-3 py-2 text-sm ${
                      isActive
                        ? "bg-accent-soft font-semibold text-accent"
                        : "text-ink hover:bg-surface-sunken"
                    }`
                  }
                >
                  <ADMIN_NAV_ITEM.icon aria-hidden className="h-5 w-5 shrink-0" strokeWidth={1.8} />
                  {t(ADMIN_NAV_ITEM.labelKey)}
                </NavLink>
              </li>
            )}
          </ul>
        </nav>
        {user && (
          <div className="border-t border-line px-4 py-3">
            <div className="flex items-center gap-3">
              <span
                aria-hidden
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-base font-bold text-accent"
              >
                {user.name.charAt(0).toUpperCase()}
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold text-ink">{user.name}</span>
                <span className="mt-0.5 inline-block rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                  {t(`role.${user.role}`)}
                </span>
              </span>
            </div>
          </div>
        )}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-3 border-b border-line bg-surface-raised px-6 py-3">
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
