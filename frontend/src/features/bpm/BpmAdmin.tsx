import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus, Trash2 } from "lucide-react";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { PageHeader } from "../../components/PageHeader";
import { Badge, Button, EmptyState, SectionCard, Skeleton, Switch } from "../../components/ui";
import { useDepartmentOptions } from "../contracts/queries";
import { useUserOptions } from "../tasks/queries";
import { taskTypeLabel } from "../tasks/labels";
import { t } from "../../i18n";
import { formatDateTime } from "../../lib/format";

type Workflow = components["schemas"]["BpmWorkflow"];
type WorkflowInput = components["schemas"]["BpmWorkflowInput"];
type StepInput = components["schemas"]["BpmStepInput"];

const TRIGGERS = ["contract_created", "status_reached", "manual"] as const;
const TASK_TYPES = [
  "review",
  "extension",
  "settlement",
  "guarantee_return",
  "report",
  "meeting",
  "other",
] as const;
const KINDS = ["user", "department", "role"] as const;
const ROLES = ["admin", "procurement_manager", "dept_manager", "employee"] as const;

function triggerLabel(trigger: string): string {
  if (trigger === "contract_created") return t("bpm.trigger.contract_created");
  if (trigger === "status_reached") return t("bpm.trigger.status_reached");
  return t("bpm.trigger.manual");
}

function kindLabel(kind: string): string {
  if (kind === "user") return t("bpm.assignee.user");
  if (kind === "department") return t("bpm.assignee.department");
  return t("bpm.assignee.role");
}

function roleLabel(role: string): string {
  if (role === "admin") return t("bpm.role.admin");
  if (role === "procurement_manager") return t("bpm.role.procurement_manager");
  if (role === "dept_manager") return t("bpm.role.dept_manager");
  return t("bpm.role.employee");
}

function stripStepMeta(step: components["schemas"]["BpmStep"]): StepInput {
  const copy: Record<string, unknown> = { ...step };
  delete copy.id;
  delete copy.position;
  return copy as StepInput;
}

const EMPTY_STEP: StepInput = {
  title: "",
  task_type: "review",
  priority: "normal",
  offset_days: 0,
  assignee_kind: "user",
};

/** Processos BPM (specs/bpm.md): seqüències de tasques per expedient.
 *  Targetes a tot l'ample i apilades, mai en graella. */
export function BpmAdmin() {
  const queryClient = useQueryClient();
  const departments = useDepartmentOptions();
  const users = useUserOptions(true);

  const workflows = useQuery({
    queryKey: ["bpm-workflows"],
    queryFn: async () => {
      const { data, error } = await api.GET("/bpm/workflows");
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const instances = useQuery({
    queryKey: ["bpm-instances"],
    refetchInterval: 60_000,
    queryFn: async () => {
      const { data, error } = await api.GET("/bpm/instances");
      if (error !== undefined) throw error;
      return data.data;
    },
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["bpm-workflows"] });
    void queryClient.invalidateQueries({ queryKey: ["bpm-instances"] });
  };

  const [editing, setEditing] = useState<Workflow | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async ({ id, body }: { id: number | null; body: WorkflowInput }) => {
      const result =
        id === null
          ? await api.POST("/bpm/workflows", { body })
          : await api.PUT("/bpm/workflows/{id}", { params: { path: { id } }, body });
      if (result.error !== undefined) throw result.error;
    },
    onSuccess: () => {
      invalidate();
      setEditing(null);
      setError(null);
    },
    onError: (err) => setError((err as { title?: string }).title ?? String(err)),
  });

  const remove = useMutation({
    mutationFn: async (id: number) => {
      const { error: err } = await api.DELETE("/bpm/workflows/{id}", {
        params: { path: { id } },
      });
      if (err !== undefined) throw err;
    },
    onSuccess: invalidate,
  });

  const toggleActive = useMutation({
    mutationFn: async (workflow: Workflow) => {
      const { error: err } = await api.PUT("/bpm/workflows/{id}", {
        params: { path: { id: workflow.id } },
        body: {
          name: workflow.name,
          description: workflow.description,
          trigger: workflow.trigger,
          trigger_status: workflow.trigger_status,
          active: !workflow.active,
          steps: workflow.steps.map((step) => stripStepMeta(step)),
        },
      });
      if (err !== undefined) throw err;
    },
    onSuccess: invalidate,
  });

  const cancelInstance = useMutation({
    mutationFn: async (id: number) => {
      const { error: err } = await api.POST("/bpm/instances/{id}/actions/cancel", {
        params: { path: { id } },
      });
      if (err !== undefined) throw err;
    },
    onSuccess: invalidate,
  });

  const workflowName = (id: number) =>
    workflows.data?.find((w) => w.id === id)?.name ?? `#${id}`;

  return (
    <div>
      <PageHeader backTo="/admin" icon={GitBranch} title={t("bpm.title")} subtitle={t("bpm.intro")} />
      <p className="mt-2 text-xs text-muted">{t("bpm.scanHint")}</p>

      <div className="mt-5 space-y-4">
        <SectionCard title={t("bpm.title")}>
          {workflows.isPending ? (
            <Skeleton rows={4} />
          ) : (workflows.data ?? []).length === 0 ? (
            <p className="text-sm text-muted">{t("bpm.noWorkflows")}</p>
          ) : (
            <ul className="divide-y divide-line">
              {(workflows.data ?? []).map((workflow) => (
                <li key={workflow.id} className="py-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <Switch
                      checked={workflow.active}
                      label={t("bpm.field.active")}
                      onChange={() => toggleActive.mutate(workflow)}
                    />
                    <span className="font-medium text-ink">{workflow.name}</span>
                    <Badge tone="accent">{triggerLabel(workflow.trigger)}</Badge>
                    {workflow.trigger_status && (
                      <span className="text-xs text-muted">«{workflow.trigger_status}»</span>
                    )}
                    <span className="ml-auto flex gap-2">
                      <Button onClick={() => setEditing(workflow)}>{t("bpm.edit")}</Button>
                      <Button
                        tone="danger"
                        onClick={() => {
                          if (window.confirm(t("bpm.deleteConfirm")))
                            remove.mutate(workflow.id);
                        }}
                      >
                        {t("bpm.delete")}
                      </Button>
                    </span>
                  </div>
                  <ol className="mt-2 space-y-0.5 text-sm text-muted">
                    {workflow.steps.map((step) => (
                      <li key={step.id}>
                        {step.position}. {step.title} · {taskTypeLabel(step.task_type ?? "other")} ·
                        +{step.offset_days ?? 0} dies · {kindLabel(step.assignee_kind)}
                        {step.assignee_kind === "user" &&
                          `: ${users.data?.find((u) => u.id === step.assignee_user_id)?.name ?? `#${step.assignee_user_id}`}`}
                        {step.assignee_kind === "department" &&
                          `: ${departments.data?.find((d) => d.id === step.assignee_department_id)?.name ?? `#${step.assignee_department_id}`}`}
                        {step.assignee_kind === "role" &&
                          `: ${roleLabel(step.assignee_role ?? "")}`}
                      </li>
                    ))}
                  </ol>
                </li>
              ))}
            </ul>
          )}
          {editing === null && (
            <div className="mt-3">
              <Button tone="accent" onClick={() => setEditing("new")}>
                <Plus aria-hidden className="mr-1 inline h-4 w-4 -translate-y-px" />
                {t("bpm.new")}
              </Button>
            </div>
          )}
          {editing !== null && (
            <WorkflowForm
              key={editing === "new" ? "new" : editing.id}
              workflow={editing === "new" ? null : editing}
              error={error}
              pending={save.isPending}
              onCancel={() => {
                setEditing(null);
                setError(null);
              }}
              onSave={(body) =>
                save.mutate({ id: editing === "new" ? null : editing.id, body })
              }
            />
          )}
        </SectionCard>

        <SectionCard title={t("bpm.instances.title")}>
          {instances.isPending ? (
            <Skeleton rows={3} />
          ) : (instances.data ?? []).length === 0 ? (
            <p className="text-sm text-muted">{t("bpm.instances.none")}</p>
          ) : (
            <ul className="divide-y divide-line">
              {(instances.data ?? []).map((instance) => (
                <li key={instance.id} className="flex flex-wrap items-center gap-3 py-2">
                  <span className="font-medium text-ink">
                    {workflowName(instance.workflow_id)}
                  </span>
                  <Link
                    to={`/contracts/${instance.contract_id}`}
                    className="text-sm text-accent underline-offset-2 hover:underline"
                  >
                    #{instance.contract_id}
                  </Link>
                  <Badge
                    tone={
                      instance.status === "running"
                        ? "accent"
                        : instance.status === "done"
                          ? "success"
                          : "neutral"
                    }
                  >
                    {instance.status === "running"
                      ? t("bpm.status.running")
                      : instance.status === "done"
                        ? t("bpm.status.done")
                        : t("bpm.status.cancelled")}
                  </Badge>
                  <span className="text-xs text-muted">
                    {t("bpm.instances.step")} {instance.current_position}
                    {instance.started_at ? ` · ${formatDateTime(instance.started_at)}` : ""}
                  </span>
                  {instance.status === "running" && (
                    <span className="ml-auto">
                      <Button
                        disabled={cancelInstance.isPending}
                        onClick={() => cancelInstance.mutate(instance.id)}
                      >
                        {t("bpm.instances.cancel")}
                      </Button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      {workflows.isError && <EmptyState icon="⚠️" title={t("admin.loadError")} />}
    </div>
  );
}

function WorkflowForm(props: {
  workflow: Workflow | null;
  error: string | null;
  pending: boolean;
  onSave: (body: WorkflowInput) => void;
  onCancel: () => void;
}) {
  const departments = useDepartmentOptions();
  const users = useUserOptions(true);
  const w = props.workflow;

  const [name, setName] = useState(w?.name ?? "");
  const [description, setDescription] = useState(w?.description ?? "");
  const [trigger, setTrigger] = useState<(typeof TRIGGERS)[number]>(
    (w?.trigger as (typeof TRIGGERS)[number]) ?? "contract_created",
  );
  const [triggerStatus, setTriggerStatus] = useState(w?.trigger_status ?? "");
  const [steps, setSteps] = useState<StepInput[]>(
    w?.steps.map((step) => stripStepMeta(step)) ?? [{ ...EMPTY_STEP }],
  );

  function patchStep(index: number, patch: Partial<StepInput>) {
    setSteps(steps.map((step, i) => (i === index ? { ...step, ...patch } : step)));
  }

  const valid =
    name.trim().length >= 2 &&
    steps.length >= 1 &&
    steps.every(
      (step) =>
        step.title.trim().length >= 2 &&
        ((step.assignee_kind === "user" && step.assignee_user_id != null) ||
          (step.assignee_kind === "department" && step.assignee_department_id != null) ||
          (step.assignee_kind === "role" && step.assignee_role != null)),
    ) &&
    (trigger !== "status_reached" || triggerStatus.trim() !== "");

  return (
    <div className="mt-3 rounded-md border border-accent/40 p-3">
      {props.error && (
        <p role="alert" className="mb-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
          {props.error}
        </p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-sm text-ink">
          {t("bpm.field.name")}
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-sm text-ink">
          {t("bpm.field.trigger")}
          <select
            value={trigger}
            onChange={(e) => setTrigger(e.target.value as (typeof TRIGGERS)[number])}
            className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          >
            {TRIGGERS.map((option) => (
              <option key={option} value={option}>
                {triggerLabel(option)}
              </option>
            ))}
          </select>
        </label>
        {trigger === "status_reached" && (
          <label className="text-sm text-ink sm:col-span-2">
            {t("bpm.field.triggerStatus")}
            <input
              value={triggerStatus}
              onChange={(e) => setTriggerStatus(e.target.value)}
              placeholder="Formalitzat"
              className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            />
          </label>
        )}
        <label className="text-sm text-ink sm:col-span-2">
          {t("bpm.field.description")}
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
      </div>

      <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-accent">
        {t("bpm.steps.title")}
      </h4>
      <ol className="mt-2 space-y-3">
        {steps.map((step, index) => (
          <li key={index} className="rounded-md border border-line bg-surface p-2.5">
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-sm text-ink sm:col-span-2">
                {index + 1}. {t("bpm.step.title")}
                <input
                  value={step.title}
                  onChange={(e) => patchStep(index, { title: e.target.value })}
                  className="mt-1 w-full rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm"
                />
              </label>
              <label className="text-sm text-ink">
                {t("tasks.field.type")}
                <select
                  value={step.task_type ?? "other"}
                  onChange={(e) =>
                    patchStep(index, { task_type: e.target.value as StepInput["task_type"] })
                  }
                  className="mt-1 w-full rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm"
                >
                  {TASK_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {taskTypeLabel(type)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-ink">
                {t("bpm.step.offsetDays")}
                <input
                  type="number"
                  min={0}
                  max={365}
                  value={step.offset_days ?? 0}
                  onChange={(e) => patchStep(index, { offset_days: Number(e.target.value) })}
                  className="mt-1 w-full rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm"
                />
              </label>
              <label className="text-sm text-ink">
                {t("bpm.step.assigneeKind")}
                <select
                  value={step.assignee_kind}
                  onChange={(e) =>
                    patchStep(index, {
                      assignee_kind: e.target.value as StepInput["assignee_kind"],
                      assignee_user_id: null,
                      assignee_department_id: null,
                      assignee_role: null,
                    })
                  }
                  className="mt-1 w-full rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm"
                >
                  {KINDS.map((kind) => (
                    <option key={kind} value={kind}>
                      {kindLabel(kind)}
                    </option>
                  ))}
                </select>
              </label>
              {step.assignee_kind === "user" && (
                <label className="text-sm text-ink">
                  {t("bpm.assignee.user")}
                  <select
                    value={step.assignee_user_id ?? ""}
                    onChange={(e) =>
                      patchStep(index, { assignee_user_id: Number(e.target.value) || null })
                    }
                    className="mt-1 w-full rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm"
                  >
                    <option value="">—</option>
                    {(users.data ?? []).map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {step.assignee_kind === "department" && (
                <label className="text-sm text-ink">
                  {t("bpm.assignee.department")}
                  <select
                    value={step.assignee_department_id ?? ""}
                    onChange={(e) =>
                      patchStep(index, {
                        assignee_department_id: Number(e.target.value) || null,
                      })
                    }
                    className="mt-1 w-full rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm"
                  >
                    <option value="">—</option>
                    {(departments.data ?? []).map((dept) => (
                      <option key={dept.id} value={dept.id}>
                        {dept.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {step.assignee_kind === "role" && (
                <label className="text-sm text-ink">
                  {t("bpm.assignee.role")}
                  <select
                    value={step.assignee_role ?? ""}
                    onChange={(e) =>
                      patchStep(index, {
                        assignee_role: (e.target.value || null) as StepInput["assignee_role"],
                      })
                    }
                    className="mt-1 w-full rounded-md border border-line bg-surface-raised px-2 py-1.5 text-sm"
                  >
                    <option value="">—</option>
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {roleLabel(role)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
            {steps.length > 1 && (
              <button
                type="button"
                className="mt-2 text-xs text-muted hover:text-danger"
                onClick={() => setSteps(steps.filter((_, i) => i !== index))}
              >
                <Trash2 aria-hidden className="mr-1 inline h-3 w-3 -translate-y-px" />
                {t("bpm.steps.remove")}
              </button>
            )}
          </li>
        ))}
      </ol>
      <div className="mt-2">
        <Button onClick={() => setSteps([...steps, { ...EMPTY_STEP }])}>
          <Plus aria-hidden className="mr-1 inline h-4 w-4 -translate-y-px" />
          {t("bpm.steps.add")}
        </Button>
      </div>

      <div className="mt-4 flex gap-2">
        <Button
          tone="accent"
          disabled={props.pending || !valid}
          onClick={() =>
            props.onSave({
              name: name.trim(),
              description: description.trim() || null,
              trigger,
              trigger_status: trigger === "status_reached" ? triggerStatus.trim() : null,
              active: w?.active ?? true,
              steps,
            })
          }
        >
          {t("admin.save")}
        </Button>
        <Button onClick={props.onCancel}>{t("admin.cancel")}</Button>
      </div>
    </div>
  );
}
