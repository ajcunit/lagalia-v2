import { Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { RefreshCw } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatDateTime } from "../../lib/format";

type SyncRun = components["schemas"]["SyncRun"];
type Kind = SyncRun["kind"];

const KINDS: Kind[] = ["contracts", "minor", "cpv", "extensions", "enrichment"];

function statusBadge(status: SyncRun["status"]) {
  const tone = status === "success" ? "accent" : status === "running" ? "neutral" : "danger";
  return <Badge tone={tone}>{t(`sync.status.${status}`)}</Badge>;
}

function duration(run: SyncRun): string {
  if (!run.started_at || !run.finished_at) return "—";
  const seconds = Math.round(
    (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000,
  );
  if (seconds < 60) return `${seconds} s`;
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

function RunItems(props: { runId: number }) {
  const items = useQuery({
    queryKey: ["sync-run-items", props.runId],
    queryFn: async () => {
      const { data, error } = await api.GET("/sync-runs/{id}/items", {
        params: { path: { id: props.runId }, query: { "page[size]": 50 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
  if (items.isPending) return <Skeleton rows={2} />;
  if (items.isError) return <p className="text-sm text-muted">{t("admin.loadError")}</p>;
  if (items.data.data.length === 0) {
    return <p className="text-sm text-muted">{t("sync.itemsEmpty")}</p>;
  }
  return (
    <div>
      <p className="text-xs text-muted">
        {t("sync.itemsCount", { shown: String(items.data.data.length), total: String(items.data.meta.total) })}
      </p>
      <table className="mt-1 w-full text-xs">
        <thead>
          <tr className="text-left text-muted">
            <th scope="col" className="py-1 pr-2 font-medium">{t("sync.item.fileCode")}</th>
            <th scope="col" className="py-1 pr-2 font-medium">{t("sync.item.outcome")}</th>
            <th scope="col" className="py-1 font-medium">{t("sync.item.message")}</th>
          </tr>
        </thead>
        <tbody>
          {items.data.data.map((item) => (
            <tr key={item.id} className="border-t border-line align-top">
              <td className="py-1 pr-2 font-mono">{item.file_code ?? "—"}</td>
              <td className="py-1 pr-2">{item.outcome ?? "—"}</td>
              <td className="py-1">{item.message ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function SyncAdmin() {
  const { permissions } = useAuth();
  const canExecute = permissions?.actions.includes("sync:execute") ?? false;
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const runs = useQuery({
    queryKey: ["sync-runs"],
    queryFn: async () => {
      const { data, error } = await api.GET("/sync-runs", {
        params: { query: { "page[size]": 25 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.data.some((run) => run.status === "running") ? 5000 : false,
  });

  const trigger = useMutation({
    mutationFn: async (kind: Kind) => {
      const { data, error, response } = await api.POST("/sync-runs/actions/trigger", {
        body: { kind },
      });
      if (error !== undefined) throw Object.assign(new Error(), { problem: error, status: response.status });
      return data;
    },
    onSuccess: (result) => {
      setNotice(t("sync.triggered", { type: result.job_type }));
      void queryClient.invalidateQueries({ queryKey: ["sync-runs"] });
    },
    onError: (error: Error & { status?: number }) => {
      setNotice(
        error.status === 409 ? t("sync.alreadyQueued") : t("sync.triggerError"),
      );
    },
  });

  function launch(kind: Kind) {
    if (kind === "enrichment" && !window.confirm(t("sync.confirmEnrichment"))) return;
    setNotice(null);
    trigger.mutate(kind);
  }

  return (
    <div>
      <PageHeader icon={RefreshCw} title={t("sync.title")} subtitle={t("sync.intro")} />

      {canExecute && (
        <div className="mt-4 flex flex-wrap gap-2">
          {KINDS.map((kind) => (
            <Button key={kind} disabled={trigger.isPending} onClick={() => launch(kind)}>
              {t(`sync.launch.${kind}`)}
            </Button>
          ))}
        </div>
      )}
      {notice && (
        <p role="status" className="mt-3 rounded-md bg-accent-soft p-2 text-sm text-ink">
          {notice}
        </p>
      )}

      <div className="mt-4 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {runs.isPending ? (
          <div className="p-4">
            <Skeleton rows={6} />
          </div>
        ) : runs.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : runs.data.data.length === 0 ? (
          <EmptyState icon="🔄" title={t("sync.empty")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.col.kind")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.col.status")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.col.trigger")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.col.started")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.col.duration")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.col.counts")}</th>
                <th scope="col" className="px-3 py-2 font-medium">
                  <span className="sr-only">{t("sync.col.details")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.data.data.map((run) => (
                <Fragment key={run.id}>
                  <tr className="border-t border-line align-top">
                    <td className="px-3 py-1.5 font-medium">{t(`sync.kind.${run.kind}`)}</td>
                    <td className="px-3 py-1.5">{statusBadge(run.status)}</td>
                    <td className="px-3 py-1.5">{t(`sync.trigger.${run.trigger}`)}</td>
                    <td className="whitespace-nowrap px-3 py-1.5">
                      {run.started_at ? formatDateTime(run.started_at) : "—"}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5">{duration(run)}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 font-mono text-xs">
                      +{run.new_count} / ~{run.updated_count} / ={run.unchanged_count}
                      {run.total_source !== null && run.total_source !== undefined
                        ? ` (${run.total_source})`
                        : ""}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <button
                        type="button"
                        className="text-xs text-muted underline"
                        onClick={() => setExpanded(expanded === run.id ? null : run.id)}
                      >
                        {expanded === run.id ? t("sync.hideDetails") : t("sync.showDetails")}
                      </button>
                    </td>
                  </tr>
                  {expanded === run.id && (
                    <tr className="border-t border-line bg-surface">
                      <td colSpan={7} className="px-3 py-2">
                        {run.error_summary && Object.keys(run.error_summary).length > 0 && (
                          <pre className="mb-2 overflow-x-auto rounded bg-danger/10 p-2 text-xs">
                            {JSON.stringify(run.error_summary, null, 2)}
                          </pre>
                        )}
                        <RunItems runId={run.id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
