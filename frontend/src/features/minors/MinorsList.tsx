import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, EmptyState, Skeleton } from "../../components/ui";
import { useDepartmentOptions } from "../contracts/queries";
import { Receipt } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";
import { useMinorContracts, type MinorsListParams } from "./queries";

type SortCol = { key: string; labelKey: Parameters<typeof t>[0] };

const COL_FILE: SortCol = { key: "file_code", labelKey: "minors.col.fileCode" };
const COL_AMOUNT: SortCol = { key: "award_amount", labelKey: "minors.col.amount" };
const COL_DATE: SortCol = { key: "award_date", labelKey: "minors.col.awardDate" };

export function MinorsList() {
  const { permissions } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [cursorStack, setCursorStack] = useState<string[]>([]);

  const q = searchParams.get("q") ?? "";
  const [search, setSearch] = useState(q);
  const sort = searchParams.get("sort") ?? "-award_date";
  const view = searchParams.get("view") ?? "user";
  const cursor = searchParams.get("cursor") ?? undefined;

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

  const params: MinorsListParams = {
    "page[size]": 25,
    "page[cursor]": cursor,
    q: q || undefined,
    sort: sort as MinorsListParams["sort"],
    view: view as MinorsListParams["view"],
    "filter[fiscal_year]": numberParam(searchParams.get("year")),
    "filter[department_id]": numberParam(searchParams.get("department")),
    "filter[unassigned]": boolParam(searchParams.get("unassigned")),
    "filter[settled]": boolParam(searchParams.get("settled")),
  };
  const minors = useMinorContracts(params);
  const departments = useDepartmentOptions();

  const activeFilters = ["year", "department", "unassigned", "settled"]
    .filter((key) => searchParams.get(key))
    .concat(q ? ["q"] : []);

  function toggleSort(key: string) {
    update({ sort: sort === `-${key}` ? key : `-${key}` });
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <PageHeader icon={Receipt} title={t("minors.title")} />
          {minors.data && (
            <p className="text-sm text-muted">
              {t("minors.total", { total: minors.data.meta.total })}
            </p>
          )}
        </div>
        {permissions?.can_switch_view && (
          <div
            role="group"
            aria-label={t("contracts.viewMode")}
            className="flex rounded-md border border-line"
          >
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

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor="minors-search">
          {t("contracts.search")}
        </label>
        <input
          id="minors-search"
          type="search"
          placeholder={t("minors.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-72 rounded-md border border-line bg-surface-raised px-3 py-2 text-sm text-ink"
        />
        <input
          aria-label={t("minors.filterYear")}
          type="number"
          placeholder={t("minors.filterYear")}
          value={searchParams.get("year") ?? ""}
          onChange={(e) => update({ year: e.target.value || null })}
          className="w-28 rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink tabular-nums"
        />
        <select
          aria-label={t("contracts.filterDepartment")}
          value={searchParams.get("department") ?? ""}
          onChange={(e) => update({ department: e.target.value || null })}
          className="rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink"
        >
          <option value="">{t("contracts.filterDepartment")}</option>
          {departments.data?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <select
          aria-label={t("minors.filterSettled")}
          value={searchParams.get("settled") ?? ""}
          onChange={(e) => update({ settled: e.target.value || null })}
          className="rounded-md border border-line bg-surface-raised px-2 py-2 text-sm text-ink"
        >
          <option value="">{t("minors.filterSettled")}</option>
          <option value="true">{t("minors.settledYes")}</option>
          <option value="false">{t("minors.settledNo")}</option>
        </select>
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
        {minors.isPending ? (
          <div className="px-4">
            <Skeleton rows={10} />
          </div>
        ) : minors.isError ? (
          <EmptyState icon="⚠️" title={t("contracts.loadError")} />
        ) : minors.data.data.length === 0 ? (
          <EmptyState title={t("minors.empty")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <SortHeader col={COL_FILE} sort={sort} onSort={toggleSort} />
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("minors.col.description")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("contracts.col.contractor")}
                </th>
                <SortHeader col={COL_AMOUNT} sort={sort} onSort={toggleSort} />
                <SortHeader col={COL_DATE} sort={sort} onSort={toggleSort} />
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("minors.col.year")}
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("minors.col.settlement")}
                </th>
              </tr>
            </thead>
            <tbody>
              {minors.data.data.map((minor) => (
                <tr
                  key={minor.id}
                  className="border-b border-line last:border-0 hover:bg-surface-sunken"
                >
                  <td className="px-3 py-2 whitespace-nowrap">
                    <Link
                      to={`/minor-contracts/${minor.id}`}
                      className="font-medium text-accent underline-offset-2 hover:underline"
                    >
                      {minor.file_code}
                    </Link>
                  </td>
                  <td
                    className="max-w-md truncate px-3 py-2 text-ink"
                    title={minor.description ?? ""}
                  >
                    {minor.description ?? "—"}
                  </td>
                  <td className="max-w-48 truncate px-3 py-2 text-muted">
                    {minor.contractor?.name ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-ink">
                    {formatCurrency(minor.award_amount)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-muted">
                    {formatDate(minor.award_date)}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-muted">
                    {minor.fiscal_year ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    {minor.settlement_date || minor.settlement_amount ? (
                      <Badge tone="accent">{t("minors.settledYes")}</Badge>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

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
          disabled={!minors.data?.meta.next_cursor}
          onClick={() => {
            const next = minors.data?.meta.next_cursor;
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
  if (value === "true") return true;
  if (value === "false") return false;
  return undefined;
}
