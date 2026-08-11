import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { t } from "../i18n";

function useHealth() {
  return useQuery({
    queryKey: ["health"],
    staleTime: 60_000,
    retry: 1,
    queryFn: async () => {
      const { data, error } = await api.GET("/health");
      if (error !== undefined) throw new Error("health");
      return data;
    },
  });
}

export function Dashboard() {
  const { user } = useAuth();
  const health = useHealth();

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold tracking-tight text-ink">
        {user ? t("dashboard.welcome", { name: user.name }) : t("dashboard.title")}
      </h1>
      <p className="mt-2 text-muted">{t("dashboard.intro")}</p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-line bg-surface-raised p-5 shadow-card">
          <h2 className="text-sm font-medium text-muted">{t("home.apiStatus")}</h2>
          <p className="mt-2 flex items-center gap-2 text-lg font-semibold text-ink">
            <span
              aria-hidden="true"
              className={`size-2.5 rounded-full ${
                health.isPending ? "bg-muted" : health.isError ? "bg-danger" : "bg-success"
              }`}
            />
            {health.isPending
              ? t("home.apiChecking")
              : health.isError
                ? t("home.apiOffline")
                : `${t("home.apiOnline")} · ${t("home.apiVersion", { version: health.data.version })}`}
          </p>
        </div>
        <div className="rounded-lg border border-line bg-surface-raised p-5 shadow-card">
          <h2 className="text-sm font-medium text-muted">{t("home.setupStatus")}</h2>
          <p className="mt-2 flex items-center gap-2 text-lg font-semibold text-ink">
            <span aria-hidden="true" className="size-2.5 rounded-full bg-success" />
            {t("home.ready")}
          </p>
        </div>
      </div>
    </div>
  );
}
