import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { t } from "../i18n";
import { useAuth } from "./AuthProvider";
import { useSetupStatus } from "./useSetupStatus";

/** Guard de rutes privades: /setup si cal inicialitzar, /login sense sessió. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const setup = useSetupStatus();

  if (status === "loading" || setup.isPending) {
    return (
      <p role="status" className="p-8 text-muted">
        {t("common.loading")}
      </p>
    );
  }
  if (setup.data?.needs_setup) return <Navigate to="/setup" replace />;
  if (status === "anonymous") return <Navigate to="/login" replace />;
  return children;
}
