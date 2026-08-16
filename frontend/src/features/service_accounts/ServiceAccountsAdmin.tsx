import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { KeyRound } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatDateTime } from "../../lib/format";

type ServiceAccount = components["schemas"]["ServiceAccount"];

const SCOPE_CATALOG: Array<{ value: string; labelKey: Parameters<typeof t>[0] }> = [
  { value: "contracts:read", labelKey: "sa.scope.contractsRead" },
  { value: "minor_contracts:read", labelKey: "sa.scope.minorsRead" },
  { value: "tasks:read", labelKey: "sa.scope.tasksRead" },
  { value: "contracts:export", labelKey: "sa.scope.contractsExport" },
  { value: "sync:read", labelKey: "sa.scope.syncRead" },
  { value: "departments:read", labelKey: "sa.scope.departmentsRead" },
];

function useServiceAccounts() {
  return useQuery({
    queryKey: ["service-accounts"],
    queryFn: async () => {
      const { data, error } = await api.GET("/service-accounts");
      if (error !== undefined) throw error;
      return data;
    },
  });
}

export function ServiceAccountsAdmin() {
  const queryClient = useQueryClient();
  const accounts = useServiceAccounts();
  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["service-accounts"] });

  const create = useMutation({
    mutationFn: async (body: { name: string; scopes: string[]; expires_at?: string | null }) => {
      const { data, error } = await api.POST("/service-accounts", { body });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: invalidate,
  });
  const update = useMutation({
    mutationFn: async ({ id, active }: { id: number; active: boolean }) => {
      const { data, error } = await api.PATCH("/service-accounts/{id}", {
        params: { path: { id } },
        body: { active },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.DELETE("/service-accounts/{id}", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: invalidate,
  });

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["contracts:read"]);
  const [expires, setExpires] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);

  function toggleScope(value: string) {
    setScopes((current) =>
      current.includes(value) ? current.filter((s) => s !== value) : [...current, value],
    );
  }

  function save() {
    setFormError(null);
    create.mutate(
      {
        name,
        scopes,
        expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null,
      },
      {
        onSuccess: (created) => {
          setCreating(false);
          setName("");
          setExpires("");
          setNewKey(created.key);
          void navigator.clipboard.writeText(created.key).catch(() => undefined);
        },
        onError: (error) => {
          const problem = error as { detail?: string; title?: string };
          setFormError(problem.detail ?? problem.title ?? String(error));
        },
      },
    );
  }

  function onDelete(account: ServiceAccount) {
    if (!window.confirm(t("sa.confirmDelete", { name: account.name }))) return;
    remove.mutate(account.id, {
      onError: (error) =>
        window.alert(t("contract.action.error", { message: String(error) })),
    });
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <PageHeader icon={KeyRound} title={t("sa.title")} subtitle={t("sa.intro")} />
        </div>
        {!creating && (
          <Button tone="accent" onClick={() => { setCreating(true); setNewKey(null); }}>
            {t("sa.new")}
          </Button>
        )}
      </div>

      {newKey && (
        <div role="alert" className="mt-4 rounded-lg border border-warning/50 bg-warning/10 p-4">
          <p className="font-medium text-ink">{t("sa.keyTitle")}</p>
          <p className="mt-1 text-sm text-muted">{t("sa.keyNote")}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="rounded bg-surface-sunken px-2 py-1 font-mono text-sm">{newKey}</code>
            <Button onClick={() => void navigator.clipboard.writeText(newKey).catch(() => undefined)}>
              {t("webhooks.copy")}
            </Button>
            <Button onClick={() => setNewKey(null)}>{t("webhooks.secretDone")}</Button>
          </div>
        </div>
      )}

      {creating && (
        <div className="mt-4 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card">
          <h2 className="text-lg font-semibold text-ink">{t("sa.new")}</h2>
          {formError && (
            <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
              {formError}
            </p>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-ink">
              {t("sa.field.name")}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="n8n — flux de recordatoris"
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink">
              {t("sa.field.expires")}
              <input
                type="date"
                value={expires}
                onChange={(e) => setExpires(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <fieldset className="text-sm text-ink sm:col-span-2">
              <legend>{t("sa.field.scopes")}</legend>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                {SCOPE_CATALOG.map((scope) => (
                  <label key={scope.value} className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={scopes.includes(scope.value)}
                      onChange={() => toggleScope(scope.value)}
                    />
                    {t(scope.labelKey)}
                    <code className="text-xs text-muted">{scope.value}</code>
                  </label>
                ))}
              </div>
              <p className="mt-1 text-xs text-muted">{t("sa.scopesNote")}</p>
            </fieldset>
          </div>
          <div className="mt-4 flex gap-2">
            <Button
              tone="accent"
              disabled={create.isPending || !name || scopes.length === 0}
              onClick={save}
            >
              {t("admin.save")}
            </Button>
            <Button onClick={() => setCreating(false)}>{t("admin.cancel")}</Button>
          </div>
        </div>
      )}

      <div className="mt-4 space-y-3">
        {accounts.isPending ? (
          <Skeleton rows={6} />
        ) : accounts.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : accounts.data.data.length === 0 ? (
          <EmptyState icon="🔑" title={t("sa.empty")} detail={t("sa.emptyDetail")} />
        ) : (
          accounts.data.data.map((account) => (
            <div
              key={account.id}
              className="rounded-lg border border-line bg-surface-raised p-4 shadow-card"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-ink">
                    {account.name}{" "}
                    {account.active ? (
                      <Badge tone="accent">{t("webhooks.active")}</Badge>
                    ) : (
                      <Badge tone="danger">{t("webhooks.inactive")}</Badge>
                    )}
                  </p>
                  <p className="font-mono text-sm text-muted">
                    {account.key_prefix}…
                    {account.last_used_at
                      ? ` · ${t("sa.lastUsed", { when: formatDateTime(account.last_used_at) })}`
                      : ` · ${t("sa.neverUsed")}`}
                    {account.expires_at &&
                      ` · ${t("sa.expires", { when: formatDateTime(account.expires_at) })}`}
                  </p>
                  <p className="mt-1 flex flex-wrap gap-1">
                    {account.scopes.map((scope) => (
                      <span
                        key={scope}
                        className="rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-muted"
                      >
                        {scope}
                      </span>
                    ))}
                  </p>
                </div>
                <span className="flex shrink-0 flex-wrap gap-2">
                  <Button
                    disabled={update.isPending}
                    onClick={() => update.mutate({ id: account.id, active: !account.active })}
                  >
                    {account.active ? t("webhooks.deactivate") : t("webhooks.activate")}
                  </Button>
                  <Button tone="danger" onClick={() => onDelete(account)}>
                    {t("sa.revoke")}
                  </Button>
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
