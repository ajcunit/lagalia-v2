import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { AlertTriangle, CalendarCheck, Eye, FileWarning, ListChecks } from "lucide-react";

import { api } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { t } from "../i18n";
import { useView } from "../view/useView";

/** Barra superior (specs/view-selector.md): selector de vista (tot l'ens /
 *  els meus departaments / un departament) + indicadors d'avisos. */
export function TopBar() {
  const { user, permissions } = useAuth();
  const { view, setView } = useView();
  const canSeeAll = permissions?.can_switch_view ?? false;
  const departments = user?.departments ?? [];
  // Amb una sola opció possible no hi ha res a triar: selector fora.
  const showSelector = canSeeAll || departments.length > 1;

  const notices = useQuery({
    queryKey: ["notices", view],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/me/notices", {
        params: { query: { view } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
  const n = notices.data;

  return (
    <header className="flex items-center gap-3 border-b border-line bg-surface-raised px-6 py-2.5">
      {showSelector && (
        <label className="flex items-center gap-2 text-sm text-muted">
          <Eye aria-hidden className="h-4 w-4" />
          <span className="sr-only">{t("shell.viewSelector")}</span>
          <select
            value={view}
            onChange={(e) => setView(e.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            {canSeeAll && <option value="all">{t("shell.viewAll")}</option>}
            {departments.length > 0 && (
              <option value="user">{t("shell.viewMine")}</option>
            )}
            {departments.map((d) => (
              <option key={d.id} value={`dept:${d.id}`}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="ml-auto flex items-center gap-2">
        {n !== undefined && (
          <>
            <NoticeChip
              to="/tasks"
              icon={CalendarCheck}
              count={n.tasks_open}
              label={t("shell.noticeTasks")}
            />
            {n.tasks_overdue > 0 && (
              <NoticeChip
                to="/tasks"
                icon={AlertTriangle}
                count={n.tasks_overdue}
                label={t("shell.noticeTasksOverdue")}
                tone="danger"
              />
            )}
            <NoticeChip
              to="/contracts?expiry=true"
              icon={FileWarning}
              count={n.contracts_expiring}
              label={t("shell.noticeExpiring")}
            />
            <NoticeChip
              to="/contracts"
              icon={ListChecks}
              count={n.contracts_pending_review}
              label={t("shell.noticePendingReview")}
            />
          </>
        )}
      </div>
    </header>
  );
}

function NoticeChip(props: {
  to: string;
  icon: typeof CalendarCheck;
  count: number;
  label: string;
  tone?: "danger";
}) {
  const zero = props.count === 0;
  return (
    <Link
      to={props.to}
      title={props.label}
      aria-label={`${props.label}: ${props.count}`}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
        props.tone === "danger" && !zero
          ? "border-danger/40 bg-danger/10 font-semibold text-danger"
          : zero
            ? "border-line text-muted"
            : "border-accent/40 bg-accent-soft font-semibold text-accent"
      }`}
    >
      <props.icon aria-hidden className="h-3.5 w-3.5" />
      <span className="tabular-nums">{props.count}</span>
      <span className="hidden lg:inline">{props.label}</span>
    </Link>
  );
}
