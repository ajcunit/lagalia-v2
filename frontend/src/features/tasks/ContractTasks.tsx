import { useState } from "react";
import { RefreshCw, Trash2 } from "lucide-react";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, SectionCard } from "../../components/ui";
import { t } from "../../i18n";
import { formatDate } from "../../lib/format";
import { statusLabel, taskTypeLabel } from "./labels";
import { useCreateTask, useDeleteTask, useTaskAction, useTasks, useUserOptions } from "./queries";

const TYPES = [
  "review",
  "extension",
  "settlement",
  "guarantee_return",
  "report",
  "meeting",
  "other",
] as const;

/** Periodicitats de supervisió (specs/tasks-ui.md): etiqueta amable ↔ RRULE.
 *  En completar una tasca periòdica, el servidor genera la següent. */
const RECURRENCES = [
  { key: "none", rrule: null },
  { key: "weekly", rrule: "FREQ=WEEKLY" },
  { key: "monthly", rrule: "FREQ=MONTHLY" },
  { key: "quarterly", rrule: "FREQ=MONTHLY;INTERVAL=3" },
  { key: "biannual", rrule: "FREQ=MONTHLY;INTERVAL=6" },
  { key: "yearly", rrule: "FREQ=YEARLY" },
] as const;

function recurrenceLabel(rrule: string | null | undefined): string | null {
  if (!rrule) return null;
  const known = RECURRENCES.find((r) => r.rrule === rrule);
  if (known === undefined) return t("tasks.recurrence.custom");
  if (known.key === "weekly") return t("tasks.recurrence.weekly");
  if (known.key === "monthly") return t("tasks.recurrence.monthly");
  if (known.key === "quarterly") return t("tasks.recurrence.quarterly");
  if (known.key === "biannual") return t("tasks.recurrence.biannual");
  if (known.key === "yearly") return t("tasks.recurrence.yearly");
  return t("tasks.recurrence.custom");
}

function recurrenceOptionLabel(key: (typeof RECURRENCES)[number]["key"]): string {
  switch (key) {
    case "none":
      return t("tasks.recurrence.none");
    case "weekly":
      return t("tasks.recurrence.weekly");
    case "monthly":
      return t("tasks.recurrence.monthly");
    case "quarterly":
      return t("tasks.recurrence.quarterly");
    case "biannual":
      return t("tasks.recurrence.biannual");
    case "yearly":
      return t("tasks.recurrence.yearly");
  }
}

export function ContractTasks(props: { contractId?: number; minorContractId?: number }) {
  const { permissions } = useAuth();
  const canRead = permissions?.actions.includes("tasks:read") ?? false;
  const canWrite = permissions?.actions.includes("tasks:write") ?? false;

  const tasks = useTasks({
    "page[size]": 50,
    contract_id: props.contractId,
    minor_contract_id: props.minorContractId,
  });
  const create = useCreateTask();
  const action = useTaskAction();
  const remove = useDeleteTask();
  const userOptions = useUserOptions(canWrite);

  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState<(typeof TYPES)[number]>("review");
  const [dueDate, setDueDate] = useState("");
  const [priority, setPriority] = useState<"low" | "normal" | "high">("normal");
  const [recurrence, setRecurrence] = useState<(typeof RECURRENCES)[number]["key"]>("none");
  const [assigneeIds, setAssigneeIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  if (!canRead) return null;

  function save() {
    setError(null);
    create.mutate(
      {
        title,
        task_type: taskType,
        due_date: dueDate,
        priority,
        recurrence: RECURRENCES.find((r) => r.key === recurrence)?.rrule ?? null,
        assignee_ids: assigneeIds,
        contract_id: props.contractId ?? null,
        minor_contract_id: props.minorContractId ?? null,
      },
      {
        onSuccess: () => {
          setCreating(false);
          setTitle("");
          setDueDate("");
          setRecurrence("none");
          setAssigneeIds([]);
        },
        onError: (err) => setError(String(err)),
      },
    );
  }

  const open = (tasks.data?.data ?? []).filter(
    (task) => task.status === "pending" || task.status === "in_progress",
  );
  const closed = (tasks.data?.data ?? []).filter(
    (task) => task.status === "done" || task.status === "cancelled",
  );

  return (
    <SectionCard title={`${t("tasks.section")} (${open.length})`}>
      {open.length > 0 ? (
        <ul className="space-y-1.5 text-sm">
          {open.map((task) => (
            <li
              key={task.id}
              className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-1.5 first:border-0"
            >
              <span className="min-w-0 flex-1">
                <span className="font-medium text-ink">{task.title}</span>{" "}
                <span className="text-muted">
                  · {taskTypeLabel(task.task_type)} · {formatDate(task.due_date)}
                </span>
                {task.assignees.length > 0 && (
                  <span className="text-muted">
                    {" "}
                    · {task.assignees.map((a) => a.name).join(", ")}
                  </span>
                )}{" "}
                {recurrenceLabel(task.recurrence) && (
                  <Badge tone="accent">
                    <RefreshCw aria-hidden className="mr-1 inline h-3 w-3 -translate-y-px" />
                    {recurrenceLabel(task.recurrence)}
                  </Badge>
                )}{" "}
                {task.status === "in_progress" && (
                  <Badge tone="accent">{statusLabel(task.status)}</Badge>
                )}
              </span>
              <span className="flex items-center gap-1.5">
                <Button
                  tone="accent"
                  disabled={action.isPending}
                  onClick={() => action.mutate({ id: task.id, action: "complete" })}
                >
                  {t("tasks.action.complete")}
                </Button>
                {canWrite && (
                  <button
                    type="button"
                    aria-label={`${t("tasks.delete")}: ${task.title}`}
                    disabled={remove.isPending}
                    className="rounded-md p-1.5 text-muted hover:bg-surface-sunken hover:text-danger disabled:opacity-50"
                    onClick={() => {
                      if (window.confirm(t("tasks.deleteConfirm"))) remove.mutate(task.id);
                    }}
                  >
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">{t("tasks.noneOpen")}</p>
      )}
      {closed.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          {t("tasks.closedCount", { count: closed.length })}
        </p>
      )}

      {canWrite && !creating && (
        <div className="mt-3">
          <Button onClick={() => setCreating(true)}>{t("tasks.new")}</Button>
        </div>
      )}
      {creating && (
        <div className="mt-3 rounded-md border border-accent/40 p-3">
          {error && (
            <p role="alert" className="mb-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
              {error}
            </p>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-sm text-ink sm:col-span-2">
              {t("tasks.field.title")}
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink">
              {t("tasks.field.type")}
              <select
                value={taskType}
                onChange={(e) => setTaskType(e.target.value as (typeof TYPES)[number])}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                {TYPES.map((type) => (
                  <option key={type} value={type}>
                    {taskTypeLabel(type)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-ink">
              {t("tasks.field.dueDate")}
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink">
              {t("tasks.field.priority")}
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as typeof priority)}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                <option value="low">{t("tasks.priority.low")}</option>
                <option value="normal">{t("tasks.priority.normal")}</option>
                <option value="high">{t("tasks.priority.high")}</option>
              </select>
            </label>
            <label className="text-sm text-ink">
              {t("tasks.field.recurrence")}
              <select
                value={recurrence}
                onChange={(e) =>
                  setRecurrence(e.target.value as (typeof RECURRENCES)[number]["key"])
                }
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                {RECURRENCES.map((option) => (
                  <option key={option.key} value={option.key}>
                    {recurrenceOptionLabel(option.key)}
                  </option>
                ))}
              </select>
              {recurrence !== "none" && (
                <span className="mt-1 block text-xs text-muted">{t("tasks.recurrenceHint")}</span>
              )}
            </label>
            <fieldset className="text-sm text-ink">
              <legend className="text-sm">{t("tasks.field.assignees")}</legend>
              <div className="mt-1 max-h-32 space-y-1 overflow-y-auto rounded-md border border-line bg-surface p-2">
                {(userOptions.data ?? []).map((user) => (
                  <label key={user.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={assigneeIds.includes(user.id)}
                      onChange={(e) =>
                        setAssigneeIds(
                          e.target.checked
                            ? [...assigneeIds, user.id]
                            : assigneeIds.filter((v) => v !== user.id),
                        )
                      }
                    />
                    {user.name}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <div className="mt-3 flex gap-2">
            <Button
              tone="accent"
              disabled={create.isPending || !title || !dueDate}
              onClick={save}
            >
              {t("admin.save")}
            </Button>
            <Button onClick={() => setCreating(false)}>{t("admin.cancel")}</Button>
          </div>
        </div>
      )}
    </SectionCard>
  );
}
