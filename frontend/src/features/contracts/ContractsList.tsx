import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";
import {
  downloadExport,
  useBulkAssignDepartments,
  useContracts,
  useContractsFacets,
  useCreateExport,
  useDepartmentOptions,
  useJobStatus,
  type ContractsListParams,
} from "./queries";

const SORTABLE: Array<{ key: string; labelKey: Parameters<typeof t>[0] }> = [
  { key: "file_code", labelKey: "contracts.col.fileCode" },
  { key: "published_at", labelKey: "contracts.col.published" },
  { key: "award_amount", labelKey: "contracts.col.amount" },
  { key: "calculated_end_date", labelKey: "contracts.col.end" },
];

export function ContractsList() {
  const { permissions } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [cursorStack, setCursorStack] = useState<string[]>([]);

  const q = searchParams.get("q") ?? "";
  const [search, setSearch] = useState(q);
  const sort = searchParams.get("sort") ?? "-published_at";
  const view = searchParams.get("view") ?? "user";
  const cursor = searchParams.get("cursor") ?? undefined;

  // Debounce de la cerca cap a la URL (l'estat viu a la URL, 10-ui §1.2).
  useEffect(() => {
    const handle = setTimeout(() => {
      if (search !== q) update({ q: search || null, cursor: null });
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    if (!("cursor" in changes)) next.delete("cursor");
    if (!next.get("cursor")) setCursorStack([]);
    setSearchParams(next, { replace: false });
  }

  const params: ContractsListParams = {
    "page[size]": 25,
    "page[cursor]": cursor,
    q: q || undefined,
    sort: sort as ContractsListParams["sort"],
    view: view as ContractsListParams["view"],
    "filter[department_id]": numberParam(searchParams.get("department")),
    "filter[year]": numberParam(searchParams.get("year")),
    "filter[contract_type]": searchParams.get("type") ?? undefined,
    "filter[internal_status]": (searchParams.get("internal") ??
      undefined) as ContractsListParams["filter[internal_status]"],
    "filter[status]": searchParams.get("status") ?? undefined,
    "filter[contractor_id]": numberParam(searchParams.get("contractor")),
    "filter[expiry_warning]": boolParam(searchParams.get("expiry")),
    "filter[possibly_finished]": boolParam(searchParams.get("finished")),
    "filter[unassigned]": boolParam(searchParams.get("unassigned")),
  };
  const contracts = useContracts(params);
  const departments = useDepartmentOptions();
  const facets = useContractsFacets(view as "user" | "all");

  // Exportació: encua el job amb els filtres vigents i descarrega en acabar.
  const canExport = permissions?.actions.includes("contracts:export") ?? false;
  const createExport = useCreateExport();
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const exportJob = useJobStatus(exportJobId);
  const exportStatus = exportJob.data?.status;
  useEffect(() => {
    if (exportJobId && exportStatus === "success") {
      setExportJobId(null);
      void downloadExport(exportJobId).catch((error) =>
        window.alert(t("contract.action.error", { message: String(error) })),
      );
    }
    if (exportStatus === "failed") {
      setExportJobId(null);
      window.alert(
        t("contract.action.error", { message: exportJob.data?.error ?? "error desconegut" }),
      );
    }
  }, [exportJobId, exportStatus, exportJob.data?.error]);

  const exporting =
    createExport.isPending || exportStatus === "queued" || exportStatus === "running";

  function onExport() {
    createExport.mutate(
      {
        format: "csv",
        view: view as "user" | "all",
        filters: {
          q: q || null,
          department_id: numberParam(searchParams.get("department")) ?? null,
          year: numberParam(searchParams.get("year")) ?? null,
          contract_type: searchParams.get("type"),
          status: searchParams.get("status"),
          contractor_id: numberParam(searchParams.get("contractor")) ?? null,
          internal_status: (searchParams.get("internal") ?? null) as never,
          expiry_warning: boolParam(searchParams.get("expiry")) ?? null,
          possibly_finished: boolParam(searchParams.get("finished")) ?? null,
          unassigned: boolParam(searchParams.get("unassigned")) ?? null,
        },
      },
      {
        onSuccess: (job) => setExportJobId(job.id),
        onError: (error) =>
          window.alert(t("contract.action.error", { message: String(error) })),
      },
    );
  }

  const canBulkAssign = permissions?.actions.includes("contracts:bulk_assign") ?? false;
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkDepartment, setBulkDepartment] = useState("");
  const [bulkMode, setBulkMode] = useState<"add" | "replace">("add");
  const bulkAssign = useBulkAssignDepartments();

  function toggleSelected(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const pageIds = contracts.data?.data.map((c) => c.id) ?? [];
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  function toggleAll() {
    setSelected((current) => {
      const next = new Set(current);
      if (allSelected) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });
  }

  function applyBulkAssign() {
    const departmentId = Number(bulkDepartment);
    if (!departmentId || selected.size === 0) return;
    bulkAssign.mutate(
      {
        contract_ids: [...selected],
        department_ids: [departmentId],
        mode: bulkMode,
      },
      {
        onSuccess: (result) => {
          window.alert(t("contracts.bulk.done", { updated: result.updated }));
          setSelected(new Set());
        },
        onError: (error) =>
          window.alert(t("contract.action.error", { message: String(error) })),
      },
    );
  }

  const activeFilters = ["department", "year", "type", "status", "contractor", "internal", "expiry", "finished", "unassigned"]
    .filter((key) => searchParams.get(key))
    .concat(q ? ["q"] : []);

  function toggleSort(key: string) {
    update({ sort: sort === `-${key}` ? key : `-${key}` });
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            {t("contracts.title")}
          </h1>
          {contracts.data && (
            <p className="text-sm text-muted">
              {t("contracts.total", { total: contracts.data.meta.total })}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
        {canExport && (
          <Button onClick={onExport} disabled={exporting}>
            {exporting ? t("contracts.exporting") : t("contracts.export")}
          </Button>
        )}
        {permissions?.can_switch_view && (
          <div role="group" aria-label={t("contracts.viewMode")} className="flex rounded-md border border-line">
            {(["user", "all"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => update({ view: mode === "user" ? null : mode })}
                aria-pressed={view === mode}
                className={`px-3 py-1.5 text-sm first:rounded-l-md last:rounded-r-md ${
                  view === mode ? "bg-accent text-accent-ink" : "bg-surface-raised text-ink"
                }`}
              >
                {t(mode === "user" ? "contracts.viewUser" : "contracts.viewAll")}
              </button>
            ))}
          </div>
        )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="contracts-search">
          {t("contracts.search")}
        </label>
        <input
          id="contracts-search"
          type="search"
          placeholder={t("contracts.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-72 rounded-md border border-line bg-surface-raised px-3 py-2 text-sm text-ink"
        />
        <select
          aria-label={t("contracts.filterDepartment")}
          value={searchParams.get("department") ?? ""}
          onChange={(e) => update({ department: e.target.value || null })}
          className="rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink"
        >
          <option value="">{t("contracts.filterDepartment")}</option>
          <option value="unassigned-sentinel" disabled>
            ──
          </option>
          {departments.data?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <select
          aria-label={t("contracts.filterStatus")}
          value={searchParams.get("status") ?? ""}
          onChange={(e) => update({ status: e.target.value || null })}
          className="rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink"
        >
          <option value="">{t("contracts.filterStatus")}</option>
          {facets.data?.statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          aria-label={t("contracts.filterType")}
          value={searchParams.get("type") ?? ""}
          onChange={(e) => update({ type: e.target.value || null })}
          className="rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink"
        >
          <option value="">{t("contracts.filterType")}</option>
          {facets.data?.contract_types.map((ty) => (
            <option key={ty} value={ty}>
              {ty}
            </option>
          ))}
        </select>
        <select
          aria-label={t("contracts.filterYear")}
          value={searchParams.get("year") ?? ""}
          onChange={(e) => update({ year: e.target.value || null })}
          className="rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink tabular-nums"
        >
          <option value="">{t("contracts.filterYear")}</option>
          {facets.data?.years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-ink">
          <input
            type="checkbox"
            checked={searchParams.get("expiry") === "true"}
            onChange={(e) => update({ expiry: e.target.checked ? "true" : null })}
          />
          {t("contracts.filterExpiry")}
        </label>
        <label className="flex items-center gap-1.5 text-sm text-ink">
          <input
            type="checkbox"
            checked={searchParams.get("unassigned") === "true"}
            onChange={(e) => update({ unassigned: e.target.checked ? "true" : null })}
          />
          {t("contracts.filterUnassigned")}
        </label>
        {activeFilters.length > 0 && (
          <button
            type="button"
            onClick={() => {
              setSearch("");
              setSearchParams(new URLSearchParams(view !== "user" ? { view } : {}));
            }}
            className="text-sm text-accent underline-offset-2 hover:underline"
          >
            {t("contracts.clearFilters", { count: activeFilters.length })}
          </button>
        )}
      </div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {contracts.isPending ? (
          <div className="px-4">
            <Skeleton rows={10} />
          </div>
        ) : contracts.isError ? (
          <EmptyState icon="⚠️" title={t("contracts.loadError")} />
        ) : contracts.data.data.length === 0 ? (
          <EmptyState
            title={t("contracts.empty")}
            detail={activeFilters.length ? t("contracts.emptyFiltered") : t("contracts.emptyScope")}
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                {canBulkAssign && (
                  <th scope="col" className="w-8 px-3 py-2">
                    <input
                      type="checkbox"
                      aria-label={t("contracts.bulk.selectAll")}
                      checked={allSelected}
                      onChange={toggleAll}
                    />
                  </th>
                )}
                {SORTABLE.slice(0, 1).map((col) => (
                  <SortHeader key={col.key} col={col} sort={sort} onSort={toggleSort} />
                ))}
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("contracts.col.subject")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("contracts.col.contractor")}
                </th>
                {SORTABLE.slice(1).map((col) => (
                  <SortHeader key={col.key} col={col} sort={sort} onSort={toggleSort} />
                ))}
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("contracts.col.state")}
                </th>
              </tr>
            </thead>
            <tbody>
              {contracts.data.data.map((contract) => (
                <tr key={contract.id} className="border-b border-line last:border-0 hover:bg-surface-sunken">
                  {canBulkAssign && (
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        aria-label={t("contracts.bulk.selectOne", { code: contract.file_code })}
                        checked={selected.has(contract.id)}
                        onChange={() => toggleSelected(contract.id)}
                      />
                    </td>
                  )}
                  <td className="px-3 py-2 whitespace-nowrap">
                    <Link
                      to={`/contracts/${contract.id}`}
                      className="font-medium text-accent underline-offset-2 hover:underline"
                    >
                      {contract.file_code}
                    </Link>
                    {contract.lot && <span className="ml-1 text-xs text-muted">lot {contract.lot}</span>}
                  </td>
                  <td className="max-w-md truncate px-3 py-2 text-ink" title={contract.subject ?? ""}>
                    {contract.subject ?? "—"}
                  </td>
                  <td className="max-w-48 truncate px-3 py-2 text-muted">
                    {contract.contractor?.name ?? "—"}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-muted">
                    {formatDate(contract.published_at)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-ink">
                    {formatCurrency(contract.award_amount)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-muted">
                    {formatDate(contract.calculated_end_date)}
                  </td>
                  <td className="px-3 py-2">
                    <span className="flex flex-wrap gap-1">
                      {contract.expiry_warning && (
                        <Badge tone="warning">{t("contracts.badge.expiry")}</Badge>
                      )}
                      {contract.possibly_finished && (
                        <Badge tone="danger">{t("contracts.badge.finished")}</Badge>
                      )}
                      {contract.internal_status !== "normal" && (
                        <Badge tone="accent">{contract.internal_status}</Badge>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canBulkAssign && selected.size > 0 && (
        <div
          role="toolbar"
          aria-label={t("contracts.bulk.assign")}
          className="sticky bottom-4 mt-3 flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface-raised p-3 shadow-card"
        >
          <span className="text-sm font-medium text-ink">
            {t("contracts.bulk.selected", { count: selected.size })}
          </span>
          <select
            aria-label={t("contracts.bulk.assign")}
            value={bulkDepartment}
            onChange={(e) => setBulkDepartment(e.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">{t("contracts.bulk.assign")}</option>
            {departments.data?.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <div role="group" aria-label={t("contracts.bulk.assign")} className="flex rounded-md border border-line">
            {(["add", "replace"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setBulkMode(mode)}
                aria-pressed={bulkMode === mode}
                className={`px-2.5 py-1.5 text-sm first:rounded-l-md last:rounded-r-md ${
                  bulkMode === mode ? "bg-accent text-accent-ink" : "bg-surface text-ink"
                }`}
              >
                {t(mode === "add" ? "contracts.bulk.mode.add" : "contracts.bulk.mode.replace")}
              </button>
            ))}
          </div>
          <Button
            tone="accent"
            onClick={applyBulkAssign}
            disabled={!bulkDepartment || bulkAssign.isPending}
          >
            {t("contracts.bulk.apply")}
          </Button>
          <Button onClick={() => setSelected(new Set())}>{t("contracts.bulk.cancel")}</Button>
        </div>
      )}

      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          disabled={cursorStack.length === 0}
          onClick={() => {
            const previous = cursorStack[cursorStack.length - 1] ?? "";
            setCursorStack(cursorStack.slice(0, -1));
            update({ cursor: previous || null });
          }}
          className="rounded-md border border-line bg-surface-raised px-3 py-1.5 text-sm text-ink disabled:opacity-50"
        >
          {t("contracts.prev")}
        </button>
        <button
          type="button"
          disabled={!contracts.data?.meta.next_cursor}
          onClick={() => {
            const next = contracts.data?.meta.next_cursor;
            if (!next) return;
            setCursorStack((stack) => [...stack, cursor ?? ""]);
            update({ cursor: next });
          }}
          className="rounded-md border border-line bg-surface-raised px-3 py-1.5 text-sm text-ink disabled:opacity-50"
        >
          {t("contracts.next")}
        </button>
      </div>
    </div>
  );
}

function SortHeader(props: {
  col: { key: string; labelKey: Parameters<typeof t>[0] };
  sort: string;
  onSort: (key: string) => void;
}) {
  const active = props.sort.replace("-", "") === props.col.key;
  const descending = props.sort === `-${props.col.key}`;
  return (
    <th
      scope="col"
      aria-sort={active ? (descending ? "descending" : "ascending") : "none"}
      className="px-3 py-2 font-medium"
    >
      <button
        type="button"
        onClick={() => props.onSort(props.col.key)}
        className={`inline-flex items-center gap-1 ${active ? "text-accent" : ""}`}
      >
        {t(props.col.labelKey)}
        <span aria-hidden="true">{active ? (descending ? "↓" : "↑") : ""}</span>
      </button>
    </th>
  );
}

function numberParam(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? undefined : parsed;
}

function boolParam(value: string | null): boolean | undefined {
  return value === "true" ? true : undefined;
}
