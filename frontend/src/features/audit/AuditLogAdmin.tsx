import { useState } from "react";
import { useInfiniteQuery, useMutation } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { ShieldCheck } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatDateTime } from "../../lib/format";

type AuditEntry = components["schemas"]["AuditEntry"];

type Filters = {
  action: string;
  actor_type: "" | "user" | "agent" | "system";
  success: "" | "true" | "false";
  from: string;
  to: string;
};

const EMPTY_FILTERS: Filters = { action: "", actor_type: "", success: "", from: "", to: "" };

function actorLabel(entry: AuditEntry): string {
  if (entry.actor_name) return entry.actor_name;
  if (entry.actor_id === null || entry.actor_id === undefined) {
    return t(`audit.actorType.${entry.actor_type}`);
  }
  return `${t(`audit.actorType.${entry.actor_type}`)} #${entry.actor_id}`;
}

export function AuditLogAdmin() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [verifyResult, setVerifyResult] = useState<string | null>(null);

  const entries = useInfiniteQuery({
    queryKey: ["audit-log", applied],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const { data, error } = await api.GET("/audit-log", {
        params: {
          query: {
            "page[size]": 50,
            ...(pageParam ? { "page[cursor]": pageParam } : {}),
            ...(applied.action ? { "filter[action]": applied.action } : {}),
            ...(applied.actor_type ? { "filter[actor_type]": applied.actor_type } : {}),
            ...(applied.success ? { "filter[success]": applied.success === "true" } : {}),
            ...(applied.from ? { "filter[from]": new Date(applied.from).toISOString() } : {}),
            ...(applied.to ? { "filter[to]": new Date(applied.to).toISOString() } : {}),
          },
        },
      });
      if (error !== undefined) throw error;
      return data;
    },
    getNextPageParam: (last) => last.meta.next_cursor ?? undefined,
  });

  const verify = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/audit-log/actions/verify", {});
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: (result) => {
      setVerifyResult(
        result.status === "ok"
          ? t("audit.verifyOk", { checked: String(result.checked) })
          : t("audit.verifyBroken", {
              id: String(result.first_broken_id ?? "?"),
              detail: result.detail ?? "",
            }),
      );
    },
    onError: () => setVerifyResult(t("audit.verifyError")),
  });

  const rows = entries.data?.pages.flatMap((page) => page.data) ?? [];
  const total = entries.data?.pages[0]?.meta.total ?? 0;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <PageHeader icon={ShieldCheck} title={t("audit.title")} subtitle={t("audit.intro")} />
        </div>
        <span className="ml-auto flex items-center gap-2">
          <Button disabled={verify.isPending} onClick={() => verify.mutate()}>
            {verify.isPending ? t("audit.verifying") : t("audit.verify")}
          </Button>
        </span>
      </div>
      {verifyResult && (
        <p
          role="status"
          className={`mt-3 rounded-md p-2 text-sm ${
            verifyResult.startsWith("✔") ? "bg-accent-soft text-ink" : "bg-danger/10 text-ink"
          }`}
        >
          {verifyResult}
        </p>
      )}

      <form
        className="mt-4 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setApplied(filters);
        }}
      >
        <label className="text-sm text-ink">
          {t("audit.filterAction")}
          <input
            value={filters.action}
            onChange={(e) => setFilters({ ...filters, action: e.target.value })}
            placeholder="auth."
            className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-sm"
          />
        </label>
        <label className="text-sm text-ink">
          {t("audit.filterActorType")}
          <select
            value={filters.actor_type}
            onChange={(e) =>
              setFilters({ ...filters, actor_type: e.target.value as Filters["actor_type"] })
            }
            className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          >
            <option value="">{t("audit.filterAll")}</option>
            <option value="user">{t("audit.actorType.user")}</option>
            <option value="agent">{t("audit.actorType.agent")}</option>
            <option value="system">{t("audit.actorType.system")}</option>
          </select>
        </label>
        <label className="text-sm text-ink">
          {t("audit.filterSuccess")}
          <select
            value={filters.success}
            onChange={(e) =>
              setFilters({ ...filters, success: e.target.value as Filters["success"] })
            }
            className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          >
            <option value="">{t("audit.filterAll")}</option>
            <option value="true">{t("audit.successYes")}</option>
            <option value="false">{t("audit.successNo")}</option>
          </select>
        </label>
        <label className="text-sm text-ink">
          {t("audit.filterFrom")}
          <input
            type="datetime-local"
            value={filters.from}
            onChange={(e) => setFilters({ ...filters, from: e.target.value })}
            className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm text-ink">
          {t("audit.filterTo")}
          <input
            type="datetime-local"
            value={filters.to}
            onChange={(e) => setFilters({ ...filters, to: e.target.value })}
            className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
        <Button tone="accent" onClick={() => setApplied(filters)}>
          {t("audit.applyFilters")}
        </Button>
        <span className="text-sm text-muted">{t("audit.total", { total: String(total) })}</span>
      </form>

      <div className="mt-4 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {entries.isPending ? (
          <div className="p-4">
            <Skeleton rows={8} />
          </div>
        ) : entries.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : rows.length === 0 ? (
          <EmptyState icon="🗒️" title={t("audit.empty")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.when")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.actor")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.action")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.resource")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.success")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.ip")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.details")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((entry) => (
                <tr key={entry.id} className="border-t border-line align-top">
                  <td className="whitespace-nowrap px-3 py-1.5">
                    {formatDateTime(entry.occurred_at)}
                  </td>
                  <td className="px-3 py-1.5">{actorLabel(entry)}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{entry.action}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {entry.resource_type
                      ? `${entry.resource_type}${entry.resource_id ? ` ${entry.resource_id}` : ""}`
                      : "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    {entry.success ? (
                      <Badge tone="accent">{t("audit.successYes")}</Badge>
                    ) : (
                      <Badge tone="danger">{t("audit.successNo")}</Badge>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 font-mono text-xs">
                    {entry.ip ?? "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    {entry.details && Object.keys(entry.details).length > 0 ? (
                      <details>
                        <summary className="cursor-pointer text-xs text-muted">
                          {t("audit.showDetails")}
                        </summary>
                        <pre className="mt-1 max-w-md overflow-x-auto rounded bg-surface p-2 text-xs">
                          {JSON.stringify(entry.details, null, 2)}
                        </pre>
                      </details>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {entries.hasNextPage && (
        <div className="mt-3">
          <Button disabled={entries.isFetchingNextPage} onClick={() => entries.fetchNextPage()}>
            {entries.isFetchingNextPage ? t("common.loading") : t("audit.loadMore")}
          </Button>
        </div>
      )}
    </div>
  );
}
