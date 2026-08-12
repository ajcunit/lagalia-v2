import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { SectionCard, Skeleton } from "../components/ui";
import { useContractsFacets, useContractsStats } from "../features/contracts/queries";
import { t } from "../i18n";
import { formatCurrency } from "../lib/format";

function KpiCard(props: { label: string; value: string; to: string }) {
  return (
    <Link
      to={props.to}
      className="rounded-lg border border-line bg-surface-raised p-4 shadow-card transition hover:border-accent"
    >
      <p className="text-sm text-muted">{props.label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-ink">{props.value}</p>
    </Link>
  );
}

function BarList(props: {
  items: Array<{ key: string; label: string; value: number; display: string; to: string }>;
}) {
  const max = Math.max(...props.items.map((item) => item.value), 1);
  return (
    <ul className="space-y-2">
      {props.items.map((item) => (
        <li key={item.key}>
          <Link to={item.to} className="group block">
            <span className="flex items-baseline justify-between gap-2 text-sm">
              <span className="truncate text-ink group-hover:text-accent" title={item.label}>
                {item.label}
              </span>
              <span className="shrink-0 tabular-nums text-muted">{item.display}</span>
            </span>
            <span
              aria-hidden="true"
              className="mt-1 block h-2 rounded-full bg-accent/70"
              style={{ width: `${Math.max(2, (item.value / max) * 100)}%` }}
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function Dashboard() {
  const { user, permissions } = useAuth();
  const canSeeAll = permissions?.can_switch_view ?? false;
  const view = canSeeAll ? "all" : "user";
  const [year, setYear] = useState<number | undefined>(undefined);
  const stats = useContractsStats({ view, year });
  const facets = useContractsFacets(view);

  const listBase = `/contracts?view=${view}`;
  const yearParam = year ? `&year=${year}` : "";

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            {user ? t("dashboard.welcome", { name: user.name }) : t("dashboard.title")}
          </h1>
          <p className="mt-1 text-muted">{t("dashboard.intro")}</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink">
          {t("dashboard.filterYear")}
          <select
            value={year ?? ""}
            onChange={(e) => setYear(e.target.value ? Number(e.target.value) : undefined)}
            className="rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm text-ink"
          >
            <option value="">{t("dashboard.allYears")}</option>
            {facets.data?.years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </div>

      {stats.isPending ? (
        <div className="mt-6">
          <Skeleton rows={8} />
        </div>
      ) : stats.isError || !stats.data ? (
        <p className="mt-6 text-sm text-muted">{t("dashboard.loadError")}</p>
      ) : (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard
              label={t("dashboard.kpi.total")}
              value={`${stats.data.totals.contracts.toLocaleString("ca-ES")}${
                stats.data.totals.new_this_month
                  ? ` (+${stats.data.totals.new_this_month})`
                  : ""
              }`}
              to={`${listBase}${yearParam}`}
            />
            <KpiCard
              label={t("dashboard.kpi.expiring")}
              value={stats.data.totals.expiry_warning.toLocaleString("ca-ES")}
              to={`${listBase}&expiry=true`}
            />
            <KpiCard
              label={t("dashboard.kpi.possiblyFinished")}
              value={stats.data.totals.possibly_finished.toLocaleString("ca-ES")}
              to={`${listBase}&finished=true`}
            />
            <KpiCard
              label={t("dashboard.kpi.awarded")}
              value={formatCurrency(stats.data.totals.awarded_total)}
              to={`${listBase}${yearParam}`}
            />
            <KpiCard
              label={t("dashboard.kpi.minors")}
              value={`${stats.data.minors.count.toLocaleString("ca-ES")} · ${formatCurrency(
                stats.data.minors.amount,
              )}`}
              to={`${listBase}${yearParam}`}
            />
            <KpiCard
              label={t("dashboard.kpi.contractors")}
              value={stats.data.totals.unique_contractors.toLocaleString("ca-ES")}
              to={`${listBase}${yearParam}`}
            />
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <SectionCard title={t("dashboard.topContractors")}>
              {stats.data.top_contractors.length ? (
                <BarList
                  items={stats.data.top_contractors.map((c) => ({
                    key: String(c.id),
                    label: c.name,
                    value: Number(c.amount),
                    display: formatCurrency(c.amount),
                    to: `${listBase}&contractor=${c.id}`,
                  }))}
                />
              ) : (
                <p className="text-sm text-muted">{t("dashboard.empty")}</p>
              )}
            </SectionCard>

            <SectionCard title={t("dashboard.byDepartment")}>
              {stats.data.by_department.length ? (
                <BarList
                  items={stats.data.by_department.slice(0, 10).map((d) => ({
                    key: String(d.id),
                    label: d.name,
                    value: d.count,
                    display: d.count.toLocaleString("ca-ES"),
                    to: `${listBase}&department=${d.id}`,
                  }))}
                />
              ) : (
                <p className="text-sm text-muted">{t("dashboard.empty")}</p>
              )}
            </SectionCard>
          </div>

          <div className="mt-4">
            <SectionCard title={t("dashboard.byStatus")}>
              <ul className="flex flex-wrap gap-2">
                {stats.data.by_status.map((s) => (
                  <li key={s.status}>
                    <Link
                      to={`${listBase}&status=${encodeURIComponent(s.status)}`}
                      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-sm text-ink transition hover:border-accent"
                    >
                      {s.status}
                      <span className="tabular-nums text-muted">{s.count}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </SectionCard>
          </div>
        </>
      )}
    </div>
  );
}
