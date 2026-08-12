import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { formatCurrency } from "../../lib/format";
import { useContractors, type ContractorsListParams } from "./queries";

type SortCol = { key: string; labelKey: Parameters<typeof t>[0]; numeric?: boolean };

const COL_NAME: SortCol = { key: "name", labelKey: "contractors.col.name" };
const COL_COUNT: SortCol = {
  key: "contracts_count",
  labelKey: "contractors.col.contracts",
  numeric: true,
};
const COL_TOTAL: SortCol = {
  key: "total_amount",
  labelKey: "contractors.col.total",
  numeric: true,
};

export function ContractorsList() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [cursorStack, setCursorStack] = useState<string[]>([]);

  const q = searchParams.get("q") ?? "";
  const [search, setSearch] = useState(q);
  const sort = searchParams.get("sort") ?? "-total_amount";
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

  const params: ContractorsListParams = {
    "page[size]": 25,
    "page[cursor]": cursor,
    q: q || undefined,
    sort: sort as ContractorsListParams["sort"],
  };
  const contractors = useContractors(params);

  function toggleSort(key: string) {
    update({ sort: sort === `-${key}` ? key : `-${key}` });
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            {t("contractors.title")}
          </h1>
          {contractors.data && (
            <p className="text-sm text-muted">
              {t("contractors.total", { total: contractors.data.meta.total })}
            </p>
          )}
        </div>
      </div>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("contractors.scopeNote")}</p>

      <div className="mt-4">
        <label className="sr-only" htmlFor="contractors-search">
          {t("contracts.search")}
        </label>
        <input
          id="contractors-search"
          type="search"
          placeholder={t("contractors.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-96 rounded-md border border-line bg-surface-raised px-3 py-2 text-sm text-ink"
        />
      </div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {contractors.isPending ? (
          <div className="px-4">
            <Skeleton rows={10} />
          </div>
        ) : contractors.isError ? (
          <EmptyState icon="⚠️" title={t("contracts.loadError")} />
        ) : contractors.data.data.length === 0 ? (
          <EmptyState title={t("contractors.empty")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <SortHeader col={COL_NAME} sort={sort} onSort={toggleSort} />
                <th scope="col" className="px-3 py-2 font-medium">
                  {t("contractors.col.taxId")}
                </th>
                <SortHeader col={COL_COUNT} sort={sort} onSort={toggleSort} />
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {t("contractors.col.minors")}
                </th>
                <SortHeader col={COL_TOTAL} sort={sort} onSort={toggleSort} />
              </tr>
            </thead>
            <tbody>
              {contractors.data.data.map((contractor) => (
                <tr
                  key={contractor.id}
                  className="border-b border-line last:border-0 hover:bg-surface-sunken"
                >
                  <td className="max-w-md truncate px-3 py-2" title={contractor.name}>
                    <Link
                      to={`/contractors/${contractor.id}`}
                      className="font-medium text-accent underline-offset-2 hover:underline"
                    >
                      {contractor.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap text-muted">
                    {contractor.tax_id ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-ink">
                    {contractor.contracts_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted">
                    {contractor.minor_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium text-ink">
                    {formatCurrency(contractor.total_amount)}
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
          disabled={!contractors.data?.meta.next_cursor}
          onClick={() => {
            const next = contractors.data?.meta.next_cursor;
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

function SortHeader(props: { col: SortCol; sort: string; onSort: (key: string) => void }) {
  const active = props.sort.replace("-", "") === props.col.key;
  const descending = props.sort === `-${props.col.key}`;
  return (
    <th
      scope="col"
      aria-sort={active ? (descending ? "descending" : "ascending") : "none"}
      className={`px-3 py-2 font-medium ${props.col.numeric ? "text-right" : ""}`}
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
