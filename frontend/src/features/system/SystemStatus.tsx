import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";

import { api } from "../../api/client";
import { PageHeader } from "../../components/PageHeader";
import { Badge, DefinitionList, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { formatBytes, formatDateTime } from "../../lib/format";

type CheckStatus = "ok" | "degraded" | "failing";

const STATUS_TONE: Record<CheckStatus, "success" | "warning" | "danger"> = {
  ok: "success",
  degraded: "warning",
  failing: "danger",
};

const STATUS_DOT: Record<CheckStatus, string> = {
  ok: "bg-success",
  degraded: "bg-warning",
  failing: "bg-danger",
};

function statusLabel(status: CheckStatus): string {
  if (status === "ok") return t("system.status.ok");
  if (status === "degraded") return t("system.status.degraded");
  return t("system.status.failing");
}

function serviceLabel(name: string): string {
  if (name.startsWith("connector:")) {
    return `${t("system.service.connector")} ${name.slice("connector:".length)}`;
  }
  switch (name) {
    case "database":
      return t("system.service.database");
    case "redis":
      return t("system.service.redis");
    case "storage":
      return t("system.service.storage");
    case "worker":
      return t("system.service.worker");
    case "scheduler":
      return t("system.service.scheduler");
    default:
      return name;
  }
}

function syncKindLabel(kind: string): string {
  switch (kind) {
    case "contracts":
      return t("sync.kind.contracts");
    case "minor":
      return t("sync.kind.minor");
    case "cpv":
      return t("sync.kind.cpv");
    case "extensions":
      return t("sync.kind.extensions");
    case "enrichment":
      return t("sync.kind.enrichment");
    case "execution":
      return t("sync.kind.execution");
    default:
      return kind;
  }
}

function syncStatusTone(status: string): "success" | "warning" | "danger" | "accent" {
  if (status === "success") return "success";
  if (status === "partial") return "warning";
  if (status === "failed") return "danger";
  return "accent";
}

function syncStatusLabel(status: string): string {
  switch (status) {
    case "running":
      return t("sync.status.running");
    case "success":
      return t("sync.status.success");
    case "failed":
      return t("sync.status.failed");
    case "partial":
      return t("sync.status.partial");
    default:
      return status;
  }
}

/** Estat del sistema (specs/system-status.md, B-022) + ús (B-010). Targetes
 *  a tot l'ample i apilades, mai en graella; refresc automàtic. */
export function SystemStatus() {
  const status = useQuery({
    queryKey: ["system-status"],
    refetchInterval: 15_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/system/status");
      if (error !== undefined) throw error;
      return data;
    },
  });

  const usage = useQuery({
    queryKey: ["system-usage"],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/system/usage", {
        params: { query: { days: 7 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  const data = status.data;

  return (
    <div>
      <PageHeader icon={Activity} title={t("system.title")} subtitle={t("system.subtitle")} />

      {status.isLoading && <Skeleton rows={10} />}

      {data && (
        <div className="mt-5 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={STATUS_TONE[data.status]}>
              {data.status === "ok"
                ? t("system.overall.ok")
                : data.status === "degraded"
                  ? t("system.overall.degraded")
                  : t("system.overall.failing")}
            </Badge>
            <span className="text-xs text-muted">
              {t("system.refreshedAt")}: {formatDateTime(data.generated_at)}
            </span>
          </div>

          <SectionCard title={t("system.services.title")}>
            <ul className="divide-y divide-line">
              {data.services.map((service) => (
                <li key={service.name} className="flex flex-wrap items-center gap-3 py-2.5">
                  <span
                    aria-hidden
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT[service.status]}`}
                  />
                  <span className="min-w-44 font-medium text-ink">
                    {serviceLabel(service.name)}
                  </span>
                  <Badge tone={STATUS_TONE[service.status]}>{statusLabel(service.status)}</Badge>
                  <span className="text-sm text-muted">
                    {service.detail ??
                      (service.latency_ms != null
                        ? `${t("system.services.latency")} ${service.latency_ms} ms`
                        : "")}
                  </span>
                  {service.checked_at && (
                    <span className="ml-auto text-xs text-muted">
                      {formatDateTime(service.checked_at)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </SectionCard>

          <SectionCard title={t("system.jobs.title")}>
            <DefinitionList
              items={[
                { label: t("system.jobs.queued"), value: data.jobs.queued },
                { label: t("system.jobs.running"), value: data.jobs.running },
                { label: t("system.jobs.dead"), value: data.jobs.dead },
                { label: t("system.jobs.failed24h"), value: data.jobs.failed_24h },
                { label: t("system.webhooks.pending"), value: data.webhooks.pending },
                { label: t("system.webhooks.failed24h"), value: data.webhooks.failed_24h },
              ]}
            />
            {data.jobs.running_jobs.length === 0 ? (
              <p className="mt-3 text-sm text-muted">{t("system.jobs.none")}</p>
            ) : (
              <ul className="mt-4 space-y-3">
                {data.jobs.running_jobs.map((job) => (
                  <li key={job.id}>
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-mono text-sm text-ink">{job.type}</span>
                      <span className="text-xs text-muted">
                        {job.progress_message ?? `${job.progress}%`}
                        {job.started_at ? ` · ${formatDateTime(job.started_at)}` : ""}
                      </span>
                    </div>
                    <div
                      role="progressbar"
                      aria-valuenow={job.progress}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-sunken"
                    >
                      <div
                        className="h-full rounded-full bg-accent transition-all"
                        style={{ width: `${job.progress}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title={t("system.syncs.title")}>
            {data.syncs.length === 0 ? (
              <p className="text-sm text-muted">{t("system.syncs.none")}</p>
            ) : (
              <ul className="divide-y divide-line">
                {data.syncs.map((run) => (
                  <li key={run.kind} className="flex flex-wrap items-center gap-3 py-2.5">
                    <span className="min-w-44 font-medium text-ink">
                      {syncKindLabel(run.kind)}
                    </span>
                    <Badge tone={syncStatusTone(run.status)}>{syncStatusLabel(run.status)}</Badge>
                    <span className="ml-auto text-xs text-muted">
                      {formatDateTime(run.finished_at ?? run.started_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          <SectionCard title={t("system.resources.title")}>
            <DefinitionList
              items={[
                {
                  label: t("system.resources.database"),
                  value: formatBytes(data.resources.database_bytes),
                },
                {
                  label: t("system.resources.redisMemory"),
                  value: formatBytes(data.resources.redis_memory_bytes),
                },
                { label: t("system.resources.queueDepth"), value: data.resources.queue_depth },
                {
                  label: t("system.resources.storageObjects"),
                  value:
                    data.resources.storage_objects != null
                      ? `${data.resources.storage_objects}${data.resources.storage_truncated ? ` (${t("system.resources.storageTruncated")})` : ""}`
                      : "—",
                },
                {
                  label: t("system.resources.storageBytes"),
                  value: `${formatBytes(data.resources.storage_bytes)}${
                    data.resources.storage_measured_at
                      ? ` · ${t("system.resources.measuredAt")} ${formatDateTime(data.resources.storage_measured_at)}`
                      : ""
                  }`,
                },
              ]}
            />
          </SectionCard>

          <SectionCard title={t("system.usage.title")}>
            {usage.data === undefined ? (
              <Skeleton rows={4} />
            ) : (
              <>
                <DefinitionList
                  items={[
                    {
                      label: t("system.usage.activeSessions"),
                      value: usage.data.active_sessions,
                    },
                    { label: t("system.usage.activeUsers"), value: usage.data.active_users },
                    {
                      label: t("system.usage.requests7d"),
                      value: usage.data.days.reduce((total, day) => total + day.requests, 0),
                    },
                    {
                      label: t("system.usage.errors7d"),
                      value: usage.data.days.reduce((total, day) => total + day.errors, 0),
                    },
                  ]}
                />
                {usage.data.top_endpoints.length === 0 ? (
                  <p className="mt-3 text-sm text-muted">{t("system.usage.none")}</p>
                ) : (
                  <div className="mt-4 space-y-4">
                    <div>
                      <h3 className="text-xs font-semibold text-muted uppercase">
                        {t("system.usage.topEndpoints")}
                      </h3>
                      <ul className="mt-2 divide-y divide-line">
                        {usage.data.top_endpoints.map((endpoint) => (
                          <li
                            key={endpoint.endpoint}
                            className="flex flex-wrap items-center gap-3 py-1.5"
                          >
                            <span className="font-mono text-sm text-ink">
                              {endpoint.endpoint}
                            </span>
                            <span className="ml-auto text-xs text-muted">
                              {endpoint.requests} {t("system.usage.requests")}
                              {endpoint.errors > 0
                                ? ` · ${endpoint.errors} ${t("system.usage.errors")}`
                                : ""}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    {usage.data.top_users.length > 0 && (
                      <div>
                        <h3 className="text-xs font-semibold text-muted uppercase">
                          {t("system.usage.topUsers")}
                        </h3>
                        <ul className="mt-2 divide-y divide-line">
                          {usage.data.top_users.map((user) => (
                            <li
                              key={user.user_id}
                              className="flex flex-wrap items-center gap-3 py-1.5"
                            >
                              <span className="text-sm text-ink">
                                {user.name ?? `#${user.user_id}`}
                              </span>
                              <span className="ml-auto text-xs text-muted">
                                {user.requests} {t("system.usage.requests")}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </SectionCard>
        </div>
      )}

      {status.isError && (
        <EmptyState title={t("system.title")} detail={String(status.error)} icon="⚠️" />
      )}
    </div>
  );
}
