import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { ThemeToggle } from "../components/ThemeToggle";
import { t } from "../i18n";

function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data, error } = await api.GET("/health");
      if (error !== undefined) throw new Error("health");
      return data;
    },
    staleTime: 60_000,
    retry: 1,
  });
}

function useSetupStatus() {
  return useQuery({
    queryKey: ["setup-status"],
    queryFn: async () => {
      const { data, error } = await api.GET("/setup/status");
      if (error !== undefined) throw new Error("setup");
      return data;
    },
    staleTime: 60_000,
    retry: 1,
  });
}

function StatusCard(props: { title: string; value: string; ok: boolean | null }) {
  const dotClass =
    props.ok === null ? "bg-muted" : props.ok ? "bg-success" : "bg-danger";
  return (
    <div className="rounded-lg border border-line bg-surface-raised p-5 shadow-card">
      <h2 className="text-sm font-medium text-muted">{props.title}</h2>
      <p className="mt-2 flex items-center gap-2 text-lg font-semibold text-ink">
        <span aria-hidden="true" className={`size-2.5 rounded-full ${dotClass}`} />
        {props.value}
      </p>
    </div>
  );
}

export function Home() {
  const health = useHealth();
  const setup = useSetupStatus();

  const apiValue = health.isPending
    ? t("home.apiChecking")
    : health.isError
      ? t("home.apiOffline")
      : `${t("home.apiOnline")} · ${t("home.apiVersion", { version: health.data.version })}`;

  const setupValue = setup.isPending
    ? t("home.apiChecking")
    : setup.isError
      ? t("home.apiOffline")
      : setup.data.needs_setup
        ? t("home.needsSetup")
        : t("home.ready");

  return (
    <main id="content" className="mx-auto max-w-3xl px-6 py-16">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium tracking-wide text-accent uppercase">
            {t("home.phase")}
          </p>
          <h1 className="mt-1 text-4xl font-bold tracking-tight text-ink">
            {t("app.name")}
          </h1>
          <p className="mt-2 text-muted">{t("app.tagline")}</p>
        </div>
        <ThemeToggle />
      </header>

      <section
        aria-label={t("home.apiStatus")}
        className="mt-10 grid gap-4 sm:grid-cols-2"
      >
        <StatusCard
          title={t("home.apiStatus")}
          value={apiValue}
          ok={health.isPending ? null : !health.isError}
        />
        <StatusCard
          title={t("home.setupStatus")}
          value={setupValue}
          ok={setup.isPending ? null : !setup.isError && !setup.data?.needs_setup}
        />
      </section>
    </main>
  );
}
