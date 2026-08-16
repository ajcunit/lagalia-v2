import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, DefinitionList, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { useDepartmentOptions } from "../contracts/queries";
import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatCurrency, formatDate, formatDateTime } from "../../lib/format";
import { ContractTasks } from "../tasks/ContractTasks";
import { useMinorContract, useUpdateMinorContract } from "./queries";

const INTERNAL_STATUSES = ["normal", "pending_review", "approved", "rejected"] as const;

function internalStatusLabel(value: string): string {
  switch (value) {
    case "pending_review":
      return t("minors.internal.pendingReview");
    case "approved":
      return t("minors.internal.approved");
    case "rejected":
      return t("minors.internal.rejected");
    default:
      return t("minors.internal.normal");
  }
}

function duration(minor: {
  duration_years?: number | null;
  duration_months?: number | null;
  duration_days?: number | null;
}): string {
  const parts: string[] = [];
  if (minor.duration_years) parts.push(`${minor.duration_years} anys`);
  if (minor.duration_months) parts.push(`${minor.duration_months} mesos`);
  if (minor.duration_days) parts.push(`${minor.duration_days} dies`);
  return parts.join(" i ") || "—";
}

export function MinorDetail() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const minor = useMinorContract(id);
  const update = useUpdateMinorContract(id);
  const departments = useDepartmentOptions();
  const { permissions } = useAuth();
  const canUpdate = permissions?.actions.includes("minor_contracts:update") ?? false;

  const [editing, setEditing] = useState(false);
  const [internalStatus, setInternalStatus] = useState<string>("normal");
  const [departmentIds, setDepartmentIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  if (minor.isPending) return <Skeleton rows={10} />;
  if (minor.isError || !minor.data) {
    return <EmptyState icon="🔒" title={t("minors.notFound")} />;
  }
  const data = minor.data;

  function startEditing() {
    setInternalStatus(data.internal_status);
    setDepartmentIds(data.department_ids ?? []);
    setError(null);
    setEditing(true);
  }

  function save() {
    update.mutate(
      {
        internal_status: internalStatus as (typeof INTERNAL_STATUSES)[number],
        department_ids: departmentIds,
      },
      {
        onSuccess: () => setEditing(false),
        onError: (err) => setError(String(err)),
      },
    );
  }

  const departmentNames = (data.department_ids ?? [])
    .map((deptId) => departments.data?.find((d) => d.id === deptId)?.name ?? `#${deptId}`)
    .join(", ");

  return (
    <div>
      <nav aria-label="breadcrumb" className="text-sm text-muted">
        <Link to="/minor-contracts" className="text-accent underline-offset-2 hover:underline">
          {t("minors.title")}
        </Link>
        {" / "}
        <span className="text-ink">{data.file_code}</span>
      </nav>

      <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          back
          backTo="/minor-contracts"
          title={data.file_code}
          subtitle={data.description ?? undefined}
        />
        <span className="flex items-center gap-1.5">
          {canUpdate && !editing && <Button onClick={startEditing}>{t("minors.edit")}</Button>}
          {data.internal_status !== "normal" && (
            <Badge tone="accent">{internalStatusLabel(data.internal_status)}</Badge>
          )}
        </span>
      </div>

      {editing && (
        <div className="mt-4 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card">
          <h2 className="text-lg font-semibold text-ink">{t("minors.edit")}</h2>
          {error && (
            <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
              {error}
            </p>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-ink">
              {t("minors.internalStatus")}
              <select
                value={internalStatus}
                onChange={(e) => setInternalStatus(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                {INTERNAL_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {internalStatusLabel(status)}
                  </option>
                ))}
              </select>
            </label>
            <fieldset className="text-sm text-ink">
              <legend>{t("admin.users.departments")}</legend>
              <div className="mt-1 max-h-36 space-y-1 overflow-y-auto rounded-md border border-line p-2">
                {departments.data?.map((d) => (
                  <label key={d.id} className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={departmentIds.includes(d.id)}
                      onChange={(e) =>
                        setDepartmentIds(
                          e.target.checked
                            ? [...departmentIds, d.id]
                            : departmentIds.filter((deptId) => deptId !== d.id),
                        )
                      }
                    />
                    {d.name}
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <div className="mt-4 flex gap-2">
            <Button tone="accent" onClick={save} disabled={update.isPending}>
              {t("admin.save")}
            </Button>
            <Button onClick={() => setEditing(false)}>{t("admin.cancel")}</Button>
          </div>
        </div>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <SectionCard title={t("minors.section.overview")}>
          <DefinitionList
            items={[
              { label: t("contracts.col.subject"), value: data.description },
              { label: t("contract.field.type"), value: data.contract_type },
              {
                label: t("minors.internalStatus"),
                value: internalStatusLabel(data.internal_status),
              },
              { label: t("minors.col.year"), value: data.fiscal_year ?? "—" },
              { label: t("minors.duration"), value: duration(data) },
              { label: t("admin.users.departments"), value: departmentNames || "—" },
              {
                label: t("minors.lastSynced"),
                value: data.last_synced_at ? formatDateTime(data.last_synced_at) : "—",
              },
            ]}
          />
        </SectionCard>

        <SectionCard title={t("minors.section.award")}>
          <DefinitionList
            items={[
              {
                label: t("contracts.col.contractor"),
                value: data.contractor?.name ?? "—",
              },
              { label: t("contract.field.nif"), value: data.contractor?.tax_id ?? "—" },
              { label: t("minors.col.amount"), value: formatCurrency(data.award_amount) },
              { label: t("minors.col.awardDate"), value: formatDate(data.award_date) },
            ]}
          />
        </SectionCard>

        <SectionCard title={t("minors.section.settlement")}>
          {data.settlement_date || data.settlement_amount || data.settlement_type ? (
            <DefinitionList
              items={[
                { label: t("minors.settlementType"), value: data.settlement_type },
                {
                  label: t("minors.settlementDate"),
                  value: formatDate(data.settlement_date),
                },
                {
                  label: t("minors.settlementAmount"),
                  value: formatCurrency(data.settlement_amount),
                },
              ]}
            />
          ) : (
            <p className="text-sm text-muted">{t("minors.noSettlement")}</p>
          )}
        </SectionCard>
      </div>

      <div className="mt-4">
        <ContractTasks minorContractId={id} />
      </div>
    </div>
  );
}
