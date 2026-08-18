import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { Network, Plug, SlidersHorizontal } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { SheetTabs } from "../../components/contractSheet";
import { useDepartments } from "../admin/queries";
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
  const [tab, setTab] = useState("settings");

  return (
    <div>
      <PageHeader
          backTo="/admin"
          icon={SlidersHorizontal} title={t("config.title")} subtitle={t("config.intro")} />

      <div className="mt-6">
        <SheetTabs
          tabs={[
            { key: "settings", label: t("config.settings"), icon: SlidersHorizontal },
            { key: "connectors", label: t("config.connectors"), icon: Plug },
            { key: "ldap", label: t("config.ldapTab"), icon: Network },
          ]}
          active={tab}
          onSelect={setTab}
        />
      </div>

      {tab === "connectors" && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
      )}

      {tab === "settings" && (
        <div className="mt-4 rounded-lg border border-line bg-surface-raised p-4 shadow-card">
          <SettingsTable canWrite={canWrite} />
        </div>
      )}

      {tab === "ldap" && <LdapMappingsPanel canWrite={canWrite} />}
    </div>
  );
}

/** Regles grup AD → rol o departament (specs/ldap-auth.md). El grup de rol
 *  dona accés a la plataforma; el de departament només assigna l'abast. */
function LdapMappingsPanel(props: { canWrite: boolean }) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["ldap-mappings"] });

  const connectors = useConnectors();
  const ldapConnector = connectors.data?.data.find((c) => c.slug === "ldap");

  const mappings = useQuery({
    queryKey: ["ldap-mappings"],
    queryFn: async () => {
      const { data, error } = await api.GET("/ldap/group-mappings");
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const departments = useDepartments();

  const [adGroup, setAdGroup] = useState("");
  const [kind, setKind] = useState<"role" | "department">("role");
  const [role, setRole] = useState<Role>("employee");
  const [departmentId, setDepartmentId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: async () => {
      const { error: err } = await api.POST("/ldap/group-mappings", {
        body: {
          ad_group: adGroup.trim(),
          role: kind === "role" ? role : null,
          department_id: kind === "department" ? Number(departmentId) : null,
        },
      });
      if (err !== undefined) throw err;
    },
    onSuccess: () => {
      setAdGroup("");
      setError(null);
      invalidate();
    },
    onError: (err) => setError((err as { title?: string }).title ?? t("admin.loadError")),
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      const { error: err } = await api.DELETE("/ldap/group-mappings/{mapping_id}", {
        params: { path: { mapping_id: id } },
      });
      if (err !== undefined) throw err;
    },
    onSuccess: invalidate,
  });

  const canSubmit =
    adGroup.trim().length >= 2 && (kind === "role" || departmentId !== "") && !create.isPending;

  return (
    <div className="mt-4 space-y-4">
      <p className="text-sm text-muted">{t("config.ldapIntro")}</p>

      <section aria-label={t("config.ldapConnection")}>
        <h2 className="text-lg font-semibold text-ink">{t("config.ldapConnection")}</h2>
        <div className="mt-3">
          {connectors.isPending ? (
            <Skeleton rows={4} />
          ) : ldapConnector !== undefined ? (
            <ConnectorCard connector={ldapConnector} canWrite={props.canWrite} />
          ) : (
            <EmptyState icon="⚠️" title={t("admin.loadError")} />
          )}
        </div>
      </section>

      <h2 className="pt-2 text-lg font-semibold text-ink">{t("config.ldapRules")}</h2>

      {props.canWrite && (
        <div className="rounded-lg border border-line bg-surface-raised p-4 shadow-card">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
              <span className="text-xs text-muted">{t("config.ldapGroup")}</span>
              <input
                value={adGroup}
                onChange={(e) => setAdGroup(e.target.value)}
                placeholder="CN=LAGALIA-Gestio,OU=Grups,DC=…"
                className="rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-xs"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-xs text-muted">{t("config.ldapKind")}</span>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as "role" | "department")}
                className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                <option value="role">{t("config.ldapKindRole")}</option>
                <option value="department">{t("config.ldapKindDepartment")}</option>
              </select>
            </label>
            {kind === "role" ? (
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-xs text-muted">{t("config.ldapRole")}</span>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as Role)}
                  className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
                >
                  {ROLES.map((value) => (
                    <option key={value} value={value}>
                      {t(`role.${value}` as Parameters<typeof t>[0])}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-xs text-muted">{t("config.ldapDepartment")}</span>
                <select
                  value={departmentId}
                  onChange={(e) => setDepartmentId(e.target.value)}
                  className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
                >
                  <option value="">—</option>
                  {(departments.data?.data ?? []).map((d) => (
                    <option key={d.id} value={String(d.id)}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <Button tone="accent" disabled={!canSubmit} onClick={() => create.mutate()}>
              {t("config.ldapAdd")}
            </Button>
          </div>
          {error !== null && <p className="mt-2 text-sm text-danger">{error}</p>}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {mappings.isPending ? (
          <div className="p-4"><Skeleton rows={3} /></div>
        ) : mappings.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (mappings.data ?? []).length === 0 ? (
          <p className="p-4 text-sm text-muted">{t("config.ldapEmpty")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">{t("config.ldapGroup")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("config.ldapKind")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("config.ldapMapsTo")}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  <span className="sr-only">{t("contract.documents.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {(mappings.data ?? []).map((mapping) => (
                <tr key={mapping.id} className="border-t border-line align-top">
                  <td className="px-3 py-1.5 font-mono text-xs">{mapping.ad_group}</td>
                  <td className="px-3 py-1.5">
                    <Badge tone={mapping.role !== null ? "accent" : "neutral"}>
                      {mapping.role !== null
                        ? t("config.ldapKindRole")
                        : t("config.ldapKindDepartment")}
                    </Badge>
                  </td>
                  <td className="px-3 py-1.5">
                    {mapping.role !== null
                      ? t(`role.${mapping.role}` as Parameters<typeof t>[0])
                      : (mapping.department_name ?? "—")}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {props.canWrite && (
                      <Button
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(mapping.id)}
                      >
                        {t("config.ldapRemove")}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

const ROLES = ["admin", "procurement_manager", "dept_manager", "employee"] as const;
type Role = (typeof ROLES)[number];
