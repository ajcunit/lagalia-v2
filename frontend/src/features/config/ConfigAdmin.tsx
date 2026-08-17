import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { SlidersHorizontal } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatDateTime } from "../../lib/format";

type Connector = components["schemas"]["Connector"];
type Setting = components["schemas"]["Setting"];

function useConnectors() {
  return useQuery({
    queryKey: ["connectors"],
    queryFn: async () => {
      const { data, error } = await api.GET("/connectors");
      if (error !== undefined) throw error;
      return data;
    },
  });
}

function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const { data, error } = await api.GET("/settings");
      if (error !== undefined) throw error;
      return data;
    },
  });
}

function ConnectorCard(props: { connector: Connector; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["connectors"] });
  const c = props.connector;

  const [config, setConfig] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(c.config).map(([k, v]) => [k, v === null || v === undefined ? "" : String(v)]),
    ),
  );
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [health, setHealth] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const patch = useMutation({
    mutationFn: async (body: { enabled?: boolean; config?: Record<string, unknown> }) => {
      const { data, error: err } = await api.PATCH("/connectors/{slug}", {
        params: { path: { slug: c.slug } },
        body,
      });
      if (err !== undefined) throw err;
      return data;
    },
    onSuccess: invalidate,
    onError: (err) => setError(String((err as { detail?: string }).detail ?? err)),
  });
  const putCredentials = useMutation({
    mutationFn: async (creds: Record<string, string>) => {
      const { data, error: err } = await api.PUT("/connectors/{slug}/credentials", {
        params: { path: { slug: c.slug } },
        body: { credentials: creds },
      });
      if (err !== undefined) throw err;
      return data;
    },
    onSuccess: () => {
      setCredentials({});
      invalidate();
    },
    onError: (err) => setError(String((err as { detail?: string }).detail ?? err)),
  });
  const check = useMutation({
    mutationFn: async () => {
      const { data, error: err } = await api.POST("/connectors/{slug}/actions/healthcheck", {
        params: { path: { slug: c.slug } },
      });
      if (err !== undefined) throw err;
      return data;
    },
    onSuccess: (result) => {
      setHealth(result.detail ? `${result.status}: ${result.detail}` : result.status);
      invalidate();
    },
  });
  const testEmail = useMutation({
    mutationFn: async () => {
      const { data, error: err } = await api.POST("/connectors/smtp/actions/send-test-email", {});
      if (err !== undefined) throw err;
      return data;
    },
    onSuccess: (result) => {
      setHealth(result.detail ? `${result.status}: ${result.detail}` : result.status);
    },
  });

  function saveConfig() {
    setError(null);
    const parsed: Record<string, unknown> = {};
    for (const [key, raw] of Object.entries(config)) {
      const original = c.config_defaults[key];
      if (typeof original === "boolean") parsed[key] = raw === "true" || raw === "cert";
      else if (typeof original === "number") parsed[key] = raw === "" ? original : Number(raw);
      else parsed[key] = raw === "" ? null : raw;
    }
    patch.mutate({ config: parsed });
  }

  function saveCredentials() {
    setError(null);
    const filled = Object.fromEntries(
      Object.entries(credentials).filter(([, v]) => v !== ""),
    );
    if (Object.keys(filled).length) putCredentials.mutate(filled);
  }

  return (
    <SectionCard title={`${c.name} (${c.slug})`}>
      <div className="flex flex-wrap items-center gap-2">
        {c.enabled ? (
          <Badge tone="accent">{t("webhooks.active")}</Badge>
        ) : (
          <Badge tone="danger">{t("webhooks.inactive")}</Badge>
        )}
        {c.health_status && (
          <span className="text-sm text-muted">
            {t("config.health")}: {c.health_status}
            {c.last_health_check && ` (${formatDateTime(c.last_health_check)})`}
          </span>
        )}
        {props.canWrite && (
          <span className="ml-auto flex gap-2">
            <Button
              disabled={patch.isPending}
              onClick={() => patch.mutate({ enabled: !c.enabled })}
            >
              {c.enabled ? t("webhooks.deactivate") : t("webhooks.activate")}
            </Button>
            <Button disabled={check.isPending} onClick={() => check.mutate()}>
              {t("config.checkHealth")}
            </Button>
            {c.slug === "smtp" && (
              <Button disabled={testEmail.isPending} onClick={() => testEmail.mutate()}>
                {testEmail.isPending ? t("config.sendingTestEmail") : t("config.sendTestEmail")}
              </Button>
            )}
          </span>
        )}
      </div>
      {health && <p className="mt-2 rounded-md bg-accent-soft p-2 text-sm text-ink">{health}</p>}
      {error && (
        <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
          {error}
        </p>
      )}

      {props.canWrite && (
        <>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {Object.keys(c.config_defaults).map((key) => (
              <label key={key} className="text-sm text-ink">
                <code className="text-xs text-muted">{key}</code>
                <input
                  value={config[key] ?? ""}
                  onChange={(e) => setConfig({ ...config, [key]: e.target.value })}
                  className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm font-mono"
                />
              </label>
            ))}
          </div>
          {Object.keys(c.config_defaults).length > 0 && (
            <div className="mt-2">
              <Button tone="accent" disabled={patch.isPending} onClick={saveConfig}>
                {t("config.saveConfig")}
              </Button>
            </div>
          )}

          {Object.keys(c.credentials).length > 0 && (
            <div className="mt-4 border-t border-line pt-3">
              <p className="text-sm font-medium text-ink">{t("config.credentials")}</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {Object.entries(c.credentials).map(([name, isSet]) => (
                  <label key={name} className="text-sm text-ink">
                    <code className="text-xs text-muted">{name}</code>{" "}
                    {isSet && <Badge tone="accent">{t("config.credentialSet")}</Badge>}
                    <input
                      type="password"
                      autoComplete="new-password"
                      placeholder={isSet ? "••••••••" : t("config.credentialEmpty")}
                      value={credentials[name] ?? ""}
                      onChange={(e) =>
                        setCredentials({ ...credentials, [name]: e.target.value })
                      }
                      className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm font-mono"
                    />
                  </label>
                ))}
              </div>
              <div className="mt-2">
                <Button
                  tone="accent"
                  disabled={putCredentials.isPending}
                  onClick={saveCredentials}
                >
                  {t("config.saveCredentials")}
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </SectionCard>
  );
}

function SettingsTable(props: { canWrite: boolean }) {
  const settings = useSettings();
  const queryClient = useQueryClient();
  const [edits, setEdits] = useState<Record<string, string>>({});

  const put = useMutation({
    mutationFn: async ({ key, value }: { key: string; value: unknown }) => {
      const { data, error } = await api.PUT("/settings/{key}", {
        params: { path: { key } },
        body: { value },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["settings"] }),
    onError: (error) =>
      window.alert(t("contract.action.error", { message: String(error) })),
  });

  if (settings.isPending) return <Skeleton rows={4} />;
  if (settings.isError) return <EmptyState icon="⚠️" title={t("admin.loadError")} />;

  function save(setting: Setting) {
    const raw = edits[setting.key];
    if (raw === undefined) return;
    let value: unknown = raw;
    if (raw !== "" && !Number.isNaN(Number(raw)) && typeof setting.value === "number") {
      value = Number(raw);
    }
    put.mutate({ key: setting.key, value });
    setEdits((current) => {
      const next = { ...current };
      delete next[setting.key];
      return next;
    });
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-muted">
          <th scope="col" className="py-1 pr-2 font-medium">{t("config.settingKey")}</th>
          <th scope="col" className="py-1 pr-2 font-medium">{t("config.settingValue")}</th>
          <th scope="col" className="py-1 font-medium">{t("config.settingDescription")}</th>
        </tr>
      </thead>
      <tbody>
        {settings.data.data.map((setting) => (
          <tr key={setting.key} className="border-t border-line align-top">
            <td className="py-1.5 pr-2 font-mono text-xs">{setting.key}</td>
            <td className="py-1.5 pr-2">
              {setting.is_secret ? (
                <Badge tone="neutral">
                  {setting.is_set ? t("config.secretSet") : t("config.secretEmpty")}
                </Badge>
              ) : props.canWrite ? (
                <span className="flex gap-1">
                  <input
                    value={edits[setting.key] ?? String(setting.value ?? "")}
                    onChange={(e) => setEdits({ ...edits, [setting.key]: e.target.value })}
                    placeholder={setting.placeholder ?? ""}
                    className="w-full rounded-md border border-line bg-surface px-2 py-1 text-sm font-mono"
                  />
                  {edits[setting.key] !== undefined && (
                    <Button tone="accent" disabled={put.isPending} onClick={() => save(setting)}>
                      {t("admin.save")}
                    </Button>
                  )}
                </span>
              ) : (
                <code>{String(setting.value ?? "—")}</code>
              )}
            </td>
            <td className="py-1.5 text-muted">{setting.description ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ConfigAdmin() {
  const { permissions } = useAuth();
  const canWrite = permissions?.actions.includes("config:write") ?? false;
  const connectors = useConnectors();

  return (
    <div>
      <PageHeader
          backTo="/admin"
          icon={SlidersHorizontal} title={t("config.title")} subtitle={t("config.intro")} />

      <h2 className="mt-6 text-lg font-semibold text-ink">{t("config.connectors")}</h2>
      <div className="mt-3 grid gap-4 lg:grid-cols-2">
        {connectors.isPending ? (
          <Skeleton rows={8} />
        ) : connectors.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (
          connectors.data.data.map((connector) => (
            <ConnectorCard key={connector.slug} connector={connector} canWrite={canWrite} />
          ))
        )}
      </div>

      <h2 className="mt-8 text-lg font-semibold text-ink">{t("config.settings")}</h2>
      <div className="mt-3 rounded-lg border border-line bg-surface-raised p-4 shadow-card">
        <SettingsTable canWrite={canWrite} />
      </div>
    </div>
  );
}
