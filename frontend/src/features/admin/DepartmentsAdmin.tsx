import { useEffect, useRef, useState } from "react";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, Skeleton, Switch } from "../../components/ui";
import { Network } from "lucide-react";
import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import {
  problemMessage,
  useCreateDepartment,
  useDepartments,
  useUpdateDepartment,
  type Department,
} from "./queries";

interface FormState {
  code: string;
  name: string;
  description: string;
  active: boolean;
}

const EMPTY_FORM: FormState = { code: "", name: "", description: "", active: true };

export function DepartmentsAdmin() {
  const { permissions } = useAuth();
  const canWrite = permissions?.actions.includes("departments:write") ?? false;

  const departments = useDepartments();
  const createDepartment = useCreateDepartment();
  const updateDepartment = useUpdateDepartment();

  const [editing, setEditing] = useState<Department | "new" | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing !== null) panelRef.current?.focus();
  }, [editing]);

  function openNew() {
    setForm(EMPTY_FORM);
    setFormError(null);
    setEditing("new");
  }

  function openEdit(department: Department) {
    setForm({
      code: department.code,
      name: department.name,
      description: department.description ?? "",
      active: department.active,
    });
    setFormError(null);
    setEditing(department);
  }

  function close() {
    setEditing(null);
    setFormError(null);
  }

  function save() {
    setFormError(null);
    const onError = (error: unknown) => setFormError(problemMessage(error));
    const body = {
      code: form.code,
      name: form.name,
      description: form.description || undefined,
    };
    if (editing === "new") {
      createDepartment.mutate(body, { onSuccess: close, onError });
    } else if (editing) {
      updateDepartment.mutate(
        { id: editing.id, body: { ...body, active: form.active } },
        { onSuccess: close, onError },
      );
    }
  }

  const saving = createDepartment.isPending || updateDepartment.isPending;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <PageHeader
          backTo="/admin"
          icon={Network}
          title={t("admin.departments.title")}
          subtitle={
            departments.data
              ? t("admin.departments.total", { total: departments.data.meta.total })
              : undefined
          }
        />
        {canWrite && (
          <Button tone="accent" onClick={openNew}>
            {t("admin.departments.new")}
          </Button>
        )}
      </div>

      {editing !== null && (
        <div
          ref={panelRef}
          tabIndex={-1}
          className="mt-4 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card"
        >
          <h2 className="text-lg font-semibold text-ink">
            {editing === "new"
              ? t("admin.departments.new")
              : t("admin.departments.editTitle", { name: editing.name })}
          </h2>
          {formError && (
            <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
              {formError}
            </p>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-ink">
              {t("admin.departments.code")}
              <input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink">
              {t("admin.departments.name")}
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink sm:col-span-2">
              {t("admin.departments.description")}
              <input
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            {editing !== "new" && (
              <label className="flex items-center gap-1.5 text-sm text-ink">
                <Switch
                  checked={form.active}
                  onChange={(active) => setForm({ ...form, active })}
                />
                {t("admin.departments.active")}
              </label>
            )}
          </div>
          <div className="mt-4 flex gap-2">
            <Button tone="accent" onClick={save} disabled={saving}>
              {t("admin.save")}
            </Button>
            <Button onClick={close}>{t("admin.cancel")}</Button>
          </div>
        </div>
      )}

      <div className="mt-4 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {departments.isPending ? (
          <div className="px-4">
            <Skeleton rows={6} />
          </div>
        ) : departments.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : departments.data.data.length === 0 ? (
          <EmptyState title={t("admin.departments.empty")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("admin.departments.code")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("admin.departments.name")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("admin.departments.description")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("admin.departments.state")}
                </th>
              </tr>
            </thead>
            <tbody>
              {departments.data.data.map((department) => (
                <tr
                  key={department.id}
                  className={`border-b border-line last:border-0 hover:bg-surface-sunken ${
                    canWrite ? "cursor-pointer" : ""
                  }`}
                  onClick={canWrite ? () => openEdit(department) : undefined}
                >
                  <td className="px-3 py-2 font-medium">
                    {canWrite ? (
                      <button
                        type="button"
                        className="text-accent underline-offset-2 hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          openEdit(department);
                        }}
                      >
                        {department.code}
                      </button>
                    ) : (
                      department.code
                    )}
                  </td>
                  <td className="px-3 py-2 text-ink">{department.name}</td>
                  <td className="max-w-md truncate px-3 py-2 text-muted">
                    {department.description ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    {department.active ? (
                      <Badge tone="accent">{t("admin.departments.badgeActive")}</Badge>
                    ) : (
                      <Badge tone="danger">{t("admin.departments.badgeInactive")}</Badge>
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
