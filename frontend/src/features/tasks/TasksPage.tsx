import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { formatDate } from "../../lib/format";
import { api } from "../../api/client";
import { statusLabel, taskTypeLabel } from "./labels";
import {
  useCreateTask,
  useTasksCalendar,
  useTaskAction,
  useTasks,
  useTaskSuggestions,
  type Task,
  type TaskSuggestion,
} from "./queries";

function subjectLink(task: Task): string {
  if (task.contract_id) return `/contracts/${task.contract_id}`;
  return `/minor-contracts/${task.minor_contract_id}`;
}

function isOverdue(task: Task): boolean {
  return (
    (task.status === "pending" || task.status === "in_progress") &&
    task.due_date < new Date().toISOString().slice(0, 10)
  );
}

function TaskRow(props: { task: Task }) {
  const action = useTaskAction();
  const task = props.task;
  const open = task.status === "pending" || task.status === "in_progress";
  return (
    <li className="flex flex-wrap items-center gap-3 border-t border-line py-2.5 first:border-0">
      <span
        aria-hidden="true"
        className={`size-2 shrink-0 rounded-full ${
          task.priority === "high"
            ? "bg-danger"
            : task.priority === "low"
              ? "bg-muted"
              : "bg-accent"
        }`}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-ink">{task.title}</p>
        <p className="text-sm text-muted">
          {taskTypeLabel(task.task_type)} ·{" "}
          <Link to={subjectLink(task)} className="text-accent underline-offset-2 hover:underline">
            {task.contract_id
              ? t("tasks.subject.contract")
              : t("tasks.subject.minor")}
          </Link>
          {task.assignees.length > 0 && (
            <> · {task.assignees.map((a) => a.name).join(", ")}</>
          )}
        </p>
      </div>
      <span className="flex shrink-0 items-center gap-2">
        <span className={`text-sm tabular-nums ${isOverdue(task) ? "font-semibold text-danger" : "text-muted"}`}>
          {formatDate(task.due_date)}
        </span>
        {isOverdue(task) && <Badge tone="danger">{t("tasks.overdue")}</Badge>}
        {task.status === "in_progress" && <Badge tone="accent">{statusLabel(task.status)}</Badge>}
        {!open && <Badge tone="neutral">{statusLabel(task.status)}</Badge>}
        {task.status === "pending" && (
          <Button
            disabled={action.isPending}
            onClick={() => action.mutate({ id: task.id, action: "start" })}
          >
            {t("tasks.action.start")}
          </Button>
        )}
        {open && (
          <Button
            tone="accent"
            disabled={action.isPending}
            onClick={() => action.mutate({ id: task.id, action: "complete" })}
          >
            {t("tasks.action.complete")}
          </Button>
        )}
        {!open && (
          <Button
            disabled={action.isPending}
            onClick={() => action.mutate({ id: task.id, action: "reopen" })}
          >
            {t("tasks.action.reopen")}
          </Button>
        )}
      </span>
    </li>
  );
}

function IcalButton() {
  const [busy, setBusy] = useState(false);
  async function subscribe() {
    setBusy(true);
    try {
      const { data, error } = await api.POST("/me/ical-key");
      if (error !== undefined) throw error;
      const url = `${window.location.origin}${data.url}`;
      await navigator.clipboard.writeText(url).catch(() => undefined);
      window.prompt(t("tasks.ical.copied"), url);
    } catch (err) {
      window.alert(t("contract.action.error", { message: String(err) }));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button onClick={() => void subscribe()} disabled={busy}>
      {t("tasks.ical.subscribe")}
    </Button>
  );
}

function Suggestions() {
  const [expanded, setExpanded] = useState(false);
  const { permissions } = useAuth();
  const canWrite = permissions?.actions.includes("tasks:write") ?? false;
  const suggestions = useTaskSuggestions(canWrite);
  const create = useCreateTask();

  if (!canWrite || !suggestions.data?.data.length) return null;

  function plan(suggestion: TaskSuggestion) {
    create.mutate(
      {
        title: suggestion.title,
        task_type: suggestion.task_type,
        due_date: suggestion.due_date ?? new Date().toISOString().slice(0, 10),
        contract_id: suggestion.contract_id,
        priority: "high",
      },
      {
        onError: (error) =>
          window.alert(t("contract.action.error", { message: String(error) })),
      },
    );
  }

  return (
    <div className="mt-4">
      <SectionCard title={t("tasks.suggestions.title")}>
        <ul className="space-y-2">
          {(expanded ? suggestions.data.data : suggestions.data.data.slice(0, 5)).map((suggestion) => (
            <li
              key={`${suggestion.contract_id}-${suggestion.task_type}`}
              className="flex flex-wrap items-center justify-between gap-2 text-sm"
            >
              <span className="min-w-0 flex-1">
                <Link
                  to={`/contracts/${suggestion.contract_id}`}
                  className="font-medium text-accent underline-offset-2 hover:underline"
                >
                  {suggestion.file_code}
                </Link>{" "}
                <span className="text-muted">— {suggestion.title}</span>
                {suggestion.due_date && (
                  <span className="text-muted"> ({formatDate(suggestion.due_date)})</span>
                )}
              </span>
              <Button
                tone="accent"
                disabled={create.isPending}
                onClick={() => plan(suggestion)}
              >
                {t("tasks.suggestions.plan")}
              </Button>
            </li>
          ))}
        </ul>
        {suggestions.data.data.length > 5 && (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="mt-2 text-sm text-accent underline-offset-2 hover:underline"
          >
            {expanded
              ? t("tasks.suggestions.showLess")
              : t("tasks.suggestions.showAll", { total: suggestions.data.data.length })}
          </button>
        )}
      </SectionCard>
    </div>
  );
}

function monthRange(anchor: string): { from: string; to: string; label: string } {
  const [year, month] = anchor.split("-").map(Number);
  const first = new Date(Date.UTC(year!, month! - 1, 1));
  const last = new Date(Date.UTC(year!, month!, 0));
  const label = first.toLocaleDateString("ca-ES", { month: "long", year: "numeric" });
  return {
    from: first.toISOString().slice(0, 10),
    to: last.toISOString().slice(0, 10),
    label,
  };
}

function shiftMonth(anchor: string, delta: number): string {
  const [year, month] = anchor.split("-").map(Number);
  const shifted = new Date(Date.UTC(year!, month! - 1 + delta, 1));
  return shifted.toISOString().slice(0, 7);
}

function CalendarView() {
  const [anchor, setAnchor] = useState(new Date().toISOString().slice(0, 7));
  const { from, to, label } = monthRange(anchor);
  const calendar = useTasksCalendar(from, to);

  const byDay = new Map<string, Task[]>();
  for (const task of calendar.data?.data ?? []) {
    const list = byDay.get(task.due_date) ?? [];
    list.push(task);
    byDay.set(task.due_date, list);
  }

  const firstDate = new Date(`${from}T00:00:00Z`);
  const startOffset = (firstDate.getUTCDay() + 6) % 7; // dilluns = 0
  const daysInMonth = Number(to.slice(8, 10));
  const cells: Array<string | null> = [
    ...Array.from({ length: startOffset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => `${anchor}-${String(i + 1).padStart(2, "0")}`),
  ];
  while (cells.length % 7 !== 0) cells.push(null);
  const weeks: Array<Array<string | null>> = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));

  const dayNames = ["dl", "dt", "dc", "dj", "dv", "ds", "dg"];
  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between">
        <Button onClick={() => setAnchor(shiftMonth(anchor, -1))}>←</Button>
        <h2 className="text-lg font-semibold text-ink">{label.charAt(0).toUpperCase() + label.slice(1)}</h2>
        <Button onClick={() => setAnchor(shiftMonth(anchor, 1))}>→</Button>
      </div>
      {calendar.isPending ? (
        <div className="mt-3">
          <Skeleton rows={6} />
        </div>
      ) : (
        <table className="mt-3 w-full table-fixed border-collapse text-sm">
          <thead>
            <tr>
              {dayNames.map((d) => (
                <th key={d} scope="col" className="border border-line p-1 text-xs text-muted">
                  {d}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weeks.map((week, wi) => (
              <tr key={wi}>
                {week.map((day, di) => (
                  <td
                    key={di}
                    className={`h-24 border border-line p-1 align-top ${
                      day === today ? "bg-accent-soft" : di >= 5 ? "bg-surface-sunken/50" : ""
                    }`}
                  >
                    {day && (
                      <>
                        <span className="text-xs tabular-nums text-muted">
                          {Number(day.slice(8, 10))}
                        </span>
                        <ul className="mt-0.5 space-y-0.5">
                          {(byDay.get(day) ?? []).slice(0, 3).map((task) => (
                            <li key={task.id}>
                              <Link
                                to={subjectLink(task)}
                                title={task.title}
                                className={`block truncate rounded px-1 text-xs ${
                                  task.priority === "high"
                                    ? "bg-danger/15 text-ink"
                                    : "bg-accent/15 text-ink"
                                }`}
                              >
                                {task.title}
                              </Link>
                            </li>
                          ))}
                          {(byDay.get(day) ?? []).length > 3 && (
                            <li className="text-xs text-muted">
                              +{(byDay.get(day) ?? []).length - 3}
                            </li>
                          )}
                        </ul>
                      </>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function TasksPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get("view") ?? "list";
  const status = searchParams.get("status") ?? "pending";

  const tasks = useTasks({
    "page[size]": 100,
    status: (status || undefined) as TasksListParams_status,
  });

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">{t("tasks.title")}</h1>
          {tasks.data && view === "list" && (
            <p className="text-sm text-muted">{t("tasks.total", { total: tasks.data.meta.total })}</p>
          )}
        </div>
        <span className="flex items-center gap-2">
        <IcalButton />
        <div role="group" aria-label={t("tasks.viewMode")} className="flex rounded-md border border-line">
          {(["list", "calendar"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => {
                const next = new URLSearchParams(searchParams);
                if (mode === "list") next.delete("view");
                else next.set("view", mode);
                setSearchParams(next);
              }}
              aria-pressed={view === mode}
              className={`px-3 py-1.5 text-sm first:rounded-l-md last:rounded-r-md ${
                view === mode ? "bg-accent text-accent-ink" : "bg-surface-raised text-ink"
              }`}
            >
              {t(mode === "list" ? "tasks.viewList" : "tasks.viewCalendar")}
            </button>
          ))}
        </div>
        </span>
      </div>

      {view !== "calendar" && <Suggestions />}

      {view === "calendar" ? (
        <CalendarView />
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            {["pending", "in_progress", "done", "cancelled", ""].map((candidate) => (
              <button
                key={candidate || "all"}
                type="button"
                onClick={() => {
                  const next = new URLSearchParams(searchParams);
                  if (candidate) next.set("status", candidate);
                  else next.set("status", "");
                  setSearchParams(next);
                }}
                aria-pressed={status === candidate}
                className={`rounded-full border px-3 py-1 text-sm ${
                  status === candidate
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-line bg-surface-raised text-ink"
                }`}
              >
                {candidate ? statusLabel(candidate) : t("tasks.status.all")}
              </button>
            ))}
          </div>

          <div className="mt-4 rounded-lg border border-line bg-surface-raised p-4 shadow-card">
            {tasks.isPending ? (
              <Skeleton rows={8} />
            ) : tasks.isError ? (
              <EmptyState icon="⚠️" title={t("admin.loadError")} />
            ) : tasks.data.data.length === 0 ? (
              <EmptyState icon="🗓️" title={t("tasks.empty")} />
            ) : (
              <ul>
                {tasks.data.data.map((task) => (
                  <TaskRow key={task.id} task={task} />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}

type TasksListParams_status = Parameters<typeof useTasks>[0]["status"];
