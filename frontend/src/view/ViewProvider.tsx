import { useEffect, useMemo, useState, type ReactNode } from "react";

import { useAuth } from "../auth/AuthProvider";
import { ViewContext, type ViewValue } from "./context";

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

