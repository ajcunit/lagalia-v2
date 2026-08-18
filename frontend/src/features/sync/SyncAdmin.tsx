import { Fragment, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, Skeleton, Switch } from "../../components/ui";
import { CalendarClock, Inbox, RefreshCw } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { SheetTabs } from "../../components/contractSheet";
import { t } from "../../i18n";
import { formatDateTime } from "../../lib/format";

type SyncRun = components["schemas"]["SyncRun"];
type Kind = SyncRun["kind"];

const KINDS: Kind[] = ["contracts", "minor", "cpv", "extensions", "enrichment", "execution"];

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
  const [tab, setTab] = useState("execucions");

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
      <PageHeader
          backTo="/admin"
          icon={RefreshCw} title={t("sync.title")} subtitle={t("sync.intro")} />

      <div className="mt-4">
        <SheetTabs
          tabs={[
            { key: "execucions", label: t("sync.tabRuns"), icon: RefreshCw },
            { key: "programacio", label: t("sync.tabSchedule"), icon: CalendarClock },
            { key: "jobs", label: t("sync.jobsTray"), icon: Inbox },
          ]}
          active={tab}
          onSelect={setTab}
        />
      </div>

      {tab === "execucions" && (
      <>
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

      </>
      )}

      {tab === "programacio" && <NightlyScheduleCard />}

      {tab === "jobs" && <JobsTray />}
    </div>
  );
}

/** Programació nocturna configurable (specs/sync-schedule.md): la cadena
 *  contracts → extensions → menors → execució, un cop al dia. */
function NightlyScheduleCard() {
  const { permissions } = useAuth();
  const canWrite = permissions?.actions.includes("config:write") ?? false;
  const queryClient = useQueryClient();

  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const { data, error } = await api.GET("/settings");
      if (error !== undefined) throw error;
      return data;
    },
  });
  const put = useMutation({
    mutationFn: async ({ key, value }: { key: string; value: unknown }) => {
      const { error } = await api.PUT("/settings/{key}", {
        params: { path: { key } },
        body: { value },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });

  const byKey = new Map((settings.data?.data ?? []).map((s) => [s.key, s.value]));
  const enabled = String(byKey.get("sync.nightly_enabled") ?? "true").toLowerCase() !== "false";
  const time = String(byKey.get("sync.nightly_time") ?? "02:30");
  const rawDays = byKey.get("sync.nightly_days");
  const days = new Set<number>(
    (() => {
      try {
        const parsed = typeof rawDays === "string" ? JSON.parse(rawDays) : rawDays;
        if (Array.isArray(parsed) && parsed.length > 0) return parsed.map(Number);
      } catch {
        // valor invàlid = tots els dies (mateix criteri que el backend)
      }
      return [1, 2, 3, 4, 5, 6, 7];
    })(),
  );

  const nightlyJobs = useQuery({
    queryKey: ["nightly-last"],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/jobs", {
        params: { query: { type: "sync.nightly", limit: 1 } },
      });
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const last = nightlyJobs.data?.[0];

  function toggleDay(day: number) {
    const next = new Set(days);
    if (next.has(day)) next.delete(day);
    else next.add(day);
    if (next.size === 0) return; // mai zero dies: desactiva el commutador
    put.mutate({ key: "sync.nightly_days", value: JSON.stringify([...next].sort()) });
  }

  const dayLabels = ["dl", "dt", "dc", "dj", "dv", "ds", "dg"];

  return (
    <div className="mt-4 rounded-lg border border-line bg-surface-raised p-4 shadow-card">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-ink">{t("sync.nightlyTitle")}</h2>
        {canWrite && (
          <label className="ml-auto flex items-center gap-2 text-sm">
            <Switch
              checked={enabled}
              onChange={(checked) =>
                put.mutate({ key: "sync.nightly_enabled", value: String(checked) })
              }
            />
            {t("sync.nightlyEnabled")}
          </label>
        )}
      </div>
      <p className="mt-1 text-sm text-muted">{t("sync.nightlyIntro")}</p>
      <div className="mt-3 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-xs text-muted">{t("sync.nightlyTime")}</span>
          <input
            type="time"
            defaultValue={time}
            disabled={!canWrite}
            onBlur={(e) => {
              if (e.target.value && e.target.value !== time)
                put.mutate({ key: "sync.nightly_time", value: e.target.value });
            }}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-xs text-muted">{t("sync.nightlyDays")}</span>
          <div className="flex gap-1" role="group" aria-label={t("sync.nightlyDays")}>
            {dayLabels.map((label, index) => {
              const day = index + 1;
              const active = days.has(day);
              return (
                <button
                  key={day}
                  type="button"
                  disabled={!canWrite}
                  aria-pressed={active}
                  onClick={() => toggleDay(day)}
                  className={`rounded-md border px-2 py-1 text-xs ${
                    active
                      ? "border-accent bg-accent-soft font-medium text-ink"
                      : "border-line text-muted hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        <p className="text-sm text-muted">
          {t("sync.nightlyLast")}{" "}
          {last !== undefined
            ? `${formatDateTime(last.created_at)} · ${t(`sync.jobStatus.${last.status}` as Parameters<typeof t>[0])}`
            : "—"}
        </p>
      </div>
    </div>
  );
}

/** Safata de jobs (B-009): morts, fallits i encuats, amb re-encuament manual. */
function JobsTray() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("dead");
  const jobs = useQuery({
    queryKey: ["jobs-tray", statusFilter],
    refetchInterval: 30_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/jobs", {
        params: {
          query: { status: statusFilter as "dead", limit: 50 },
        },
      });
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const requeue = useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.POST("/jobs/{id}/actions/requeue", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["jobs-tray"] }),
  });
  const requeuable = statusFilter === "dead" || statusFilter === "failed" || statusFilter === "cancelled";

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-ink">{t("sync.jobsTray")}</h2>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label={t("sync.jobsTrayFilter")}
          className="ml-auto rounded-md border border-line bg-surface px-2 py-1 text-sm"
        >
          {(["dead", "failed", "queued", "running", "cancelled"] as const).map((option) => (
            <option key={option} value={option}>
              {t(`sync.jobStatus.${option}` as Parameters<typeof t>[0])}
            </option>
          ))}
        </select>
      </div>
      <p className="mt-1 text-sm text-muted">{t("sync.jobsTrayIntro")}</p>
      <div className="mt-2 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {jobs.isPending ? (
          <div className="p-4"><Skeleton rows={2} /></div>
        ) : jobs.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (jobs.data ?? []).length === 0 ? (
          <p className="p-4 text-sm text-muted">{t("sync.jobsTrayEmpty")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.col.kind")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.when")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.jobAttempts")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("sync.jobError")}</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  <span className="sr-only">{t("contract.documents.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {(jobs.data ?? []).map((job) => (
                <tr key={job.id} className="border-t border-line align-top">
                  <td className="px-3 py-1.5 font-mono text-xs">{job.type}</td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-muted">
                    {formatDateTime(job.created_at)}
                  </td>
                  <td className="px-3 py-1.5 tabular-nums">{job.attempts ?? 0}</td>
                  <td className="max-w-md px-3 py-1.5 text-xs text-muted">
                    {job.error ?? job.progress_message ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {requeuable && (
                      <Button
                        disabled={requeue.isPending}
                        onClick={() => requeue.mutate(job.id)}
                      >
                        {t("sync.requeue")}
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
