import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { useAuth } from "../auth/AuthProvider";

/** Vista global de dades (specs/view-selector.md): "all" (tot l'ens, si el
 *  rol ho permet), "user" (els meus departaments) o "dept:<id>" (un de
 *  concret). El servidor SEMPRE revalida: això només tria què es demana. */
export type ViewValue = string;

interface ViewContextValue {
  view: ViewValue;
  setView: (view: ViewValue) => void;
}

const ViewContext = createContext<ViewContextValue | undefined>(undefined);

function storageKey(userId: number | undefined): string {
  return `lagalia.view.${userId ?? "anon"}`;
}

export function ViewProvider(props: { children: ReactNode }) {
  const { user, permissions } = useAuth();
  const canSeeAll = permissions?.can_switch_view ?? false;
  const fallback: ViewValue = canSeeAll ? "all" : "user";

  const [view, setViewState] = useState<ViewValue>(fallback);

  // En canviar d'usuari (o carregar permisos), recupera la seva última tria.
  useEffect(() => {
    const stored = localStorage.getItem(storageKey(user?.id));
    const candidate = stored ?? fallback;
    // Mai confiar en el localStorage: si la tria guardada ja no és vàlida
    // (canvi de rol o de departaments), es torna al valor segur.
    const departmentIds = new Set((user?.departments ?? []).map((d) => d.id));
    const valid =
      candidate === "user" ||
      (candidate === "all" && canSeeAll) ||
      (candidate.startsWith("dept:") &&
        (canSeeAll || departmentIds.has(Number(candidate.slice(5)))));
    setViewState(valid ? candidate : fallback);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, canSeeAll]);

  const value = useMemo(
    () => ({
      view,
      setView: (next: ViewValue) => {
        setViewState(next);
        localStorage.setItem(storageKey(user?.id), next);
      },
    }),
    [view, user?.id],
  );

  return <ViewContext.Provider value={value}>{props.children}</ViewContext.Provider>;
}

export function useView(): ViewContextValue {
  const context = useContext(ViewContext);
  if (context === undefined) throw new Error("useView requereix ViewProvider");
  return context;
}
