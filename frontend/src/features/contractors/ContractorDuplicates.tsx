import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { formatCurrency } from "../../lib/format";
import {
  useContractorDuplicates,
  useResolveDuplicate,
  type ContractorDuplicate,
} from "./queries";

const TABS = ["pending", "merged", "rejected"] as const;

function tabLabel(tab: (typeof TABS)[number]): string {
  switch (tab) {
    case "merged":
      return t("duplicates.tab.merged");
    case "rejected":
      return t("duplicates.tab.rejected");
    default:
      return t("duplicates.tab.pending");
  }
}

function Candidate(props: {
  contractor: ContractorDuplicate["contractor_1"];
  highlight?: boolean;
}) {
  const c = props.contractor;
  return (
    <div
      className={`flex-1 rounded-md border p-3 ${
        props.highlight ? "border-accent/50" : "border-line"
      }`}
    >
      <Link
        to={`/contractors/${c.id}`}
        className="font-medium text-accent underline-offset-2 hover:underline"
      >
        {c.name}
      </Link>
      <p className="mt-1 text-sm text-muted">
        {c.tax_id ?? "—"} · {c.contracts_count + c.minor_count}{" "}
        {t("duplicates.contractsShort")} · {formatCurrency(c.total_amount)}
      </p>
    </div>
  );
}

export function ContractorDuplicates() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("pending");
  const duplicates = useContractorDuplicates(tab);
  const resolve = useResolveDuplicate();
  const [busyId, setBusyId] = useState<number | null>(null);

  function act(pair: ContractorDuplicate, action: "merge_1" | "merge_2" | "reject") {
    const keep = action === "merge_1" ? pair.contractor_1 : pair.contractor_2;
    const message =
      action === "reject"
        ? t("duplicates.confirmReject")
        : t("duplicates.confirmMerge", { name: keep.name });
    if (!window.confirm(message)) return;
    setBusyId(pair.id);
    resolve.mutate(
      { id: pair.id, action },
      {
        onSettled: () => setBusyId(null),
        onError: (error) =>
          window.alert(t("contract.action.error", { message: String(error) })),
      },
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight text-ink">{t("duplicates.title")}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("duplicates.intro")}</p>

      <div role="tablist" className="mt-4 flex gap-1 border-b border-line">
        {TABS.map((candidate) => (
          <button
            key={candidate}
            role="tab"
            aria-selected={tab === candidate}
            onClick={() => setTab(candidate)}
            className={`border-b-2 px-3 py-2 text-sm ${
              tab === candidate
                ? "border-accent font-medium text-accent"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {tabLabel(candidate)}
          </button>
        ))}
      </div>

      {duplicates.data && tab === "pending" && duplicates.data.meta.total > 50 && (
        <p className="mt-3 rounded-md border border-warning/40 bg-warning/10 p-2 text-sm text-ink">
          {t("duplicates.volumeWarning", { total: duplicates.data.meta.total })}
        </p>
      )}

      <div className="mt-4 space-y-3">
        {duplicates.isPending ? (
          <Skeleton rows={8} />
        ) : duplicates.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : duplicates.data.data.length === 0 ? (
          <EmptyState icon="✅" title={t("duplicates.empty")} />
        ) : (
          duplicates.data.data.map((pair) => (
            <div
              key={pair.id}
              className="rounded-lg border border-line bg-surface-raised p-4 shadow-card"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-stretch">
                <Candidate contractor={pair.contractor_1} />
                <span aria-hidden="true" className="self-center text-muted">
                  ⇄
                </span>
                <Candidate contractor={pair.contractor_2} />
              </div>
              {tab === "pending" ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    tone="accent"
                    disabled={busyId === pair.id}
                    onClick={() => act(pair, "merge_1")}
                  >
                    {t("duplicates.mergeInto", { name: pair.contractor_1.name })}
                  </Button>
                  <Button
                    tone="accent"
                    disabled={busyId === pair.id}
                    onClick={() => act(pair, "merge_2")}
                  >
                    {t("duplicates.mergeInto", { name: pair.contractor_2.name })}
                  </Button>
                  <Button disabled={busyId === pair.id} onClick={() => act(pair, "reject")}>
                    {t("duplicates.reject")}
                  </Button>
                </div>
              ) : (
                <p className="mt-3 text-sm text-muted">
                  <Badge tone={tab === "merged" ? "accent" : "neutral"}>{tabLabel(tab)}</Badge>
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
