import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { Copy, GitMerge, Hourglass, XCircle } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { SheetTabs } from "../../components/contractSheet";
import { t } from "../../i18n";
import { formatCurrency, formatDateTime } from "../../lib/format";
import {
  useContractorDuplicates,
  useDuplicateGroups,
  useResolveGroup,
  type ContractorDuplicate,
  type ContractorDuplicateGroup,
} from "./queries";

type Tab = "pending" | "merged" | "rejected";

function tabLabel(tab: Tab): string {
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

function Group(props: { group: ContractorDuplicateGroup }) {
  const resolve = useResolveGroup();
  const members = props.group.contractors;
  const [canonical, setCanonical] = useState<number>(members[0]?.id ?? 0);

  function act(action: "merge" | "reject") {
    const keep = members.find((m) => m.id === canonical);
    const message =
      action === "reject"
        ? t("duplicates.confirmReject")
        : t("duplicates.confirmMerge", { name: keep?.name ?? "" });
    if (!window.confirm(message)) return;
    resolve.mutate(
      {
        tax_id: props.group.tax_id,
        action,
        canonical_id: action === "merge" ? canonical : null,
      },
      {
        onError: (error) =>
          window.alert(t("contract.action.error", { message: String(error) })),
      },
    );
  }

  return (
    <div className="rounded-lg border border-line bg-surface-raised p-4 shadow-card">
      <p className="text-sm font-medium text-ink">
        {t("duplicates.groupTitle", { taxId: props.group.tax_id, count: members.length })}
      </p>
      <fieldset className="mt-2">
        <legend className="sr-only">{t("duplicates.pickCanonical")}</legend>
        <ul className="space-y-1.5">
          {members.map((member) => (
            <li key={member.id} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={`canonical-${props.group.tax_id}`}
                id={`c-${props.group.tax_id}-${member.id}`}
                checked={canonical === member.id}
                onChange={() => setCanonical(member.id)}
              />
              <label htmlFor={`c-${props.group.tax_id}-${member.id}`} className="flex-1 truncate">
                <Link
                  to={`/contractors/${member.id}`}
                  className="text-accent underline-offset-2 hover:underline"
                >
                  {member.name}
                </Link>
              </label>
              <span className="shrink-0 tabular-nums text-muted">
                {member.contracts_count + member.minor_count} {t("duplicates.contractsShort")} ·{" "}
                {formatCurrency(member.total_amount)}
              </span>
            </li>
          ))}
        </ul>
      </fieldset>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button tone="accent" disabled={resolve.isPending} onClick={() => act("merge")}>
          {t("duplicates.mergeGroup")}
        </Button>
        <Button disabled={resolve.isPending} onClick={() => act("reject")}>
          {t("duplicates.rejectGroup")}
        </Button>
      </div>
    </div>
  );
}

export function ContractorDuplicates() {
  const [tab, setTab] = useState<Tab>("pending");
  const groups = useDuplicateGroups();
  const duplicates = useContractorDuplicates(tab);
  const resolve = useResolveGroup();

  return (
    <div>
      <PageHeader
          backTo="/admin"
          icon={Copy} title={t("duplicates.title")} subtitle={t("duplicates.intro")} />

      <div className="mt-4">
        <SheetTabs
          tabs={[
            { key: "pending", label: tabLabel("pending"), icon: Hourglass },
            { key: "merged", label: tabLabel("merged"), icon: GitMerge },
            { key: "rejected", label: tabLabel("rejected"), icon: XCircle },
          ]}
          active={tab}
          onSelect={(key) => setTab(key as Tab)}
        />
      </div>

      {tab === "pending" ? (
        <div className="mt-4 space-y-3">
          {groups.data && (
            <p className="text-sm text-muted">
              {t("duplicates.groupsTotal", { total: groups.data.meta.total })}
            </p>
          )}
          {groups.isPending || resolve.isPending ? (
            <Skeleton rows={8} />
          ) : groups.isError ? (
            <EmptyState icon="⚠️" title={t("admin.loadError")} />
          ) : groups.data.data.length === 0 ? (
            <EmptyState icon="✅" title={t("duplicates.empty")} />
          ) : (
            groups.data.data.map((group) => <Group key={group.tax_id} group={group} />)
          )}
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {duplicates.isPending ? (
            <Skeleton rows={8} />
          ) : duplicates.isError ? (
            <EmptyState icon="⚠️" title={t("admin.loadError")} />
          ) : duplicates.data.data.length === 0 ? (
            <EmptyState title={t("duplicates.empty")} />
          ) : (
            duplicates.data.data.map((pair: ContractorDuplicate) => (
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
                <p className="mt-3 flex items-center gap-2 text-sm text-muted">
                  <Badge tone={tab === "merged" ? "accent" : "neutral"}>{tabLabel(tab)}</Badge>
                  {pair.resolved_at && (
                    <span>
                      {t("duplicates.resolvedAt")} {formatDateTime(pair.resolved_at)}
                    </span>
                  )}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
