import { useEffect, useRef, useState } from "react";

import { ChevronUp, LogOut, Moon, Sun } from "lucide-react";

import type { components } from "../api/generated/schema";
import { t } from "../i18n";
import { useTheme } from "../theme/useTheme";

type User = components["schemas"]["User"];

/** Peu del sidebar: la targeta d'usuari és un menú desplegable amb el mode
 *  fosc i el tancament de sessió (specs/view-selector.md). */
export function UserMenu(props: { user: User; onLogout: () => void }) {
  const { theme, toggle } = useTheme();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  // Tancar en clicar fora o amb Escape.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={container} className="relative border-t border-line px-4 py-3">
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-3 right-3 mb-1 rounded-lg border border-line bg-surface-raised p-1 shadow-card"
        >
          <button
            type="button"
            role="menuitem"
            onClick={toggle}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-ink hover:bg-surface-sunken"
          >
            {theme === "dark" ? (
              <Sun aria-hidden className="h-4 w-4" />
            ) : (
              <Moon aria-hidden className="h-4 w-4" />
            )}
            {theme === "dark" ? t("theme.light") : t("theme.dark")}
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={props.onLogout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-ink hover:bg-surface-sunken"
          >
            <LogOut aria-hidden className="h-4 w-4" />
            {t("shell.logout")}
          </button>
        </div>
      )}
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 rounded-lg text-left hover:bg-surface-sunken"
      >
        <span
          aria-hidden
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-base font-bold text-accent"
        >
          {props.user.name.charAt(0).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-ink">{props.user.name}</span>
          <span className="mt-0.5 inline-block rounded-full bg-accent-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
            {t(`role.${props.user.role}`)}
          </span>
        </span>
        <ChevronUp
          aria-hidden
          className={`h-4 w-4 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
    </div>
  );
}
