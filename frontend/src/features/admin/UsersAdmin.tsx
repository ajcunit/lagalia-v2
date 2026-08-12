import { useEffect, useRef, useState } from "react";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import {
  problemMessage,
  useCreateUser,
  useDepartments,
  useUpdateUser,
  useUsers,
  type User,
} from "./queries";

const ROLES = ["admin", "procurement_manager", "dept_manager", "employee"] as const;

function roleLabel(role: string): string {
  switch (role) {
    case "admin":
      return t("admin.role.admin");
    case "procurement_manager":
      return t("admin.role.procurementManager");
    case "dept_manager":
      return t("admin.role.deptManager");
    default:
      return t("admin.role.employee");
  }
}

interface FormState {
  name: string;
  email: string;
  role: (typeof ROLES)[number];
  password: string;
  active: boolean;
  can_audit: boolean;
  can_plan: boolean;
  department_ids: number[];
}

const EMPTY_FORM: FormState = {
  name: "",
  email: "",
  role: "employee",
  password: "",
  active: true,
  can_audit: false,
  can_plan: false,
  department_ids: [],
};

export function UsersAdmin() {
  const { permissions } = useAuth();
  const canWrite = permissions?.actions.includes("users:write") ?? false;

  const [roleFilter, setRoleFilter] = useState("");
  const [onlyActive, setOnlyActive] = useState(false);
  const users = useUsers({
    "page[size]": 200,
    "filter[role]": (roleFilter || undefined) as never,
    "filter[active]": onlyActive ? true : undefined,
    sort: "name",
  });
  const departments = useDepartments();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();

  const [editing, setEditing] = useState<User | "new" | null>(null);
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

  function openEdit(user: User) {
    setForm({
      name: user.name,
      email: user.email,
      role: user.role,
      password: "",
      active: user.active,
      can_audit: user.can_audit ?? false,
      can_plan: user.can_plan ?? false,
      department_ids: (user.departments ?? []).map((d) => d.id),
    });
    setFormError(null);
    setEditing(user);
  }

  function close() {
    setEditing(null);
    setFormError(null);
  }

  function save() {
    setFormError(null);
    const onError = (error: unknown) => setFormError(problemMessage(error));
    if (editing === "new") {
      createUser.mutate(
        {
          name: form.name,
          email: form.email,
          role: form.role,
          password: form.password || undefined,
          department_ids: form.department_ids,
          can_audit: form.can_audit,
          can_plan: form.can_plan,
        },
        { onSuccess: close, onError },
      );
    } else if (editing) {
      updateUser.mutate(
        {
          id: editing.id,
          body: {
            name: form.name,
            role: form.role,
            active: form.active,
            department_ids: form.department_ids,
            can_audit: form.can_audit,
            can_plan: form.can_plan,
            ...(form.password ? { password: form.password } : {}),
          },
        },
        { onSuccess: close, onError },
      );
    }
  }

  const saving = createUser.isPending || updateUser.isPending;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">{t("admin.users.title")}</h1>
          {users.data && (
            <p className="text-sm text-muted">
              {t("admin.users.total", { total: users.data.meta.total })}
            </p>
          )}
        </div>
        {canWrite && <Button tone="accent" onClick={openNew}>{t("admin.users.new")}</Button>}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <select
          aria-label={t("admin.users.filterRole")}
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink"
        >
          <option value="">{t("admin.users.filterRole")}</option>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {roleLabel(role)}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-ink">
          <input
            type="checkbox"
            checked={onlyActive}
            onChange={(e) => setOnlyActive(e.target.checked)}
          />
          {t("admin.users.onlyActive")}
        </label>
      </div>

      {editing !== null && (
        <div
          ref={panelRef}
          tabIndex={-1}
          className="mt-4 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card"
        >
          <h2 className="text-lg font-semibold text-ink">
            {editing === "new"
              ? t("admin.users.new")
              : t("admin.users.editTitle", { name: editing.name })}
          </h2>
          {formError && (
            <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
              {formError}
            </p>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-ink">
              {t("admin.users.name")}
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink">
              {t("admin.users.email")}
              <input
                type="email"
                value={form.email}
                disabled={editing !== "new"}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm disabled:opacity-60"
              />
            </label>
            <label className="text-sm text-ink">
              {t("admin.users.role")}
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as FormState["role"] })}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {roleLabel(role)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm text-ink">
              {editing === "new" ? t("admin.users.password") : t("admin.users.passwordReset")}
              <input
                type="password"
                value={form.password}
                autoComplete="new-password"
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <fieldset className="text-sm text-ink">
              <legend>{t("admin.users.departments")}</legend>
              <div className="mt-1 max-h-36 space-y-1 overflow-y-auto rounded-md border border-line p-2">
                {departments.data?.data.map((d) => (
                  <label key={d.id} className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={form.department_ids.includes(d.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          department_ids: e.target.checked
                            ? [...form.department_ids, d.id]
                            : form.department_ids.filter((id) => id !== d.id),
                        })
                      }
                    />
                    {d.name}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="space-y-1.5 text-sm text-ink">
              {editing !== "new" && (
                <label className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(e) => setForm({ ...form, active: e.target.checked })}
                  />
                  {t("admin.users.active")}
                </label>
              )}
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={form.can_audit}
                  onChange={(e) => setForm({ ...form, can_audit: e.target.checked })}
                />
                {t("admin.users.canAudit")}
              </label>
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={form.can_plan}
                  onChange={(e) => setForm({ ...form, can_plan: e.target.checked })}
                />
                {t("admin.users.canPlan")}
              </label>
            </div>
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
        {users.isPending ? (
          <div className="px-4">
            <Skeleton rows={8} />
          </div>
        ) : users.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : users.data.data.length === 0 ? (
          <EmptyState title={t("admin.users.empty")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">{t("admin.users.name")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("admin.users.email")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("admin.users.role")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("admin.users.departments")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("admin.users.state")}</th>
              </tr>
            </thead>
            <tbody>
              {users.data.data.map((user) => (
                <tr
                  key={user.id}
                  className={`border-b border-line last:border-0 hover:bg-surface-sunken ${
                    canWrite ? "cursor-pointer" : ""
                  }`}
                  onClick={canWrite ? () => openEdit(user) : undefined}
                >
                  <td className="px-3 py-2 font-medium text-ink">
                    {canWrite ? (
                      <button
                        type="button"
                        className="text-accent underline-offset-2 hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          openEdit(user);
                        }}
                      >
                        {user.name}
                      </button>
                    ) : (
                      user.name
                    )}
                  </td>
                  <td className="px-3 py-2 text-muted">{user.email}</td>
                  <td className="px-3 py-2">{roleLabel(user.role)}</td>
                  <td className="px-3 py-2 text-muted">
                    {(user.departments ?? []).map((d) => d.name).join(", ") || "—"}
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex flex-wrap gap-1">
                      {!user.active && <Badge tone="danger">{t("admin.users.inactive")}</Badge>}
                      {user.can_audit && <Badge tone="neutral">{t("admin.users.badgeAudit")}</Badge>}
                      {user.can_plan && <Badge tone="neutral">{t("admin.users.badgePlan")}</Badge>}
                      {user.active && !user.can_audit && !user.can_plan && (
                        <span className="text-muted">—</span>
                      )}
                    </span>
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
