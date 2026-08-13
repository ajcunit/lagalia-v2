import { useState } from "react";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, SectionCard } from "../../components/ui";
import { t } from "../../i18n";
import { formatDate } from "../../lib/format";
import { statusLabel, taskTypeLabel } from "./labels";
import { useCreateTask, useTaskAction, useTasks } from "./queries";

const TYPES = [
  "review",
  "extension",
  "settlement",
  "guarantee_return",
  "report",
  "meeting",
  "other",
] as const;

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

  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [taskType, setTaskType] = useState<(typeof TYPES)[number]>("review");
  const [dueDate, setDueDate] = useState("");
  const [priority, setPriority] = useState<"low" | "normal" | "high">("normal");
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
        contract_id: props.contractId ?? null,
        minor_contract_id: props.minorContractId ?? null,
      },
      {
        onSuccess: () => {
          setCreating(false);
          setTitle("");
          setDueDate("");
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
                {task.status === "in_progress" && (
                  <Badge tone="accent">{statusLabel(task.status)}</Badge>
                )}
              </span>
              <Button
                tone="accent"
                disabled={action.isPending}
                onClick={() => action.mutate({ id: task.id, action: "complete" })}
              >
                {t("tasks.action.complete")}
              </Button>
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
