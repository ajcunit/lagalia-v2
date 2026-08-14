import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";

type Item = Record<string, unknown>;

function s(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "—";
}

function Block(props: {
  title: string;
  intro: string;
  total: number;
  items: Item[];
  columns: { key: string; label: string; render?: (item: Item) => React.ReactNode }[];
  emptyNote?: string;
}) {
  return (
    <SectionCard title={`${props.title} (${props.total})`}>
      <p className="text-sm text-muted">{props.intro}</p>
      {props.items.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{props.emptyNote ?? t("riskAudit.none")}</p>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                {props.columns.map((col) => (
                  <th key={col.key} scope="col" className="py-1 pr-3 font-medium">
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {props.items.map((item, index) => (
                <tr key={index} className="border-t border-line align-top">
                  {props.columns.map((col) => (
                    <td key={col.key} className="py-1.5 pr-3">
                      {col.render ? col.render(item) : s(item[col.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

const contractLink = (item: Item) => (
  <Link to={`/contracts/${s(item.contract_id)}`} className="font-mono text-xs text-accent underline">
    {s(item.file_code)}
  </Link>
);

export function RiskAudit() {
  const flags = useQuery({
    queryKey: ["red-flags"],
    queryFn: async () => {
      const { data, error } = await api.GET("/audit/red-flags");
      if (error !== undefined) throw error;
      return data;
    },
  });

  if (flags.isPending) return <Skeleton rows={10} />;
  if (flags.isError) return <EmptyState icon="⚠️" title={t("admin.loadError")} />;
  const d = flags.data;

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight text-ink">{t("riskAudit.title")}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("riskAudit.intro")}</p>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Block
          title={t("riskAudit.splitting")}
          intro={t("riskAudit.splittingIntro")}
          total={d.splitting.total}
          items={d.splitting.items}
          columns={[
            {
              key: "contractor_name",
              label: t("search.contractor"),
              render: (item) => (
                <Link to={`/contractors/${s(item.contractor_id)}`} className="text-accent underline">
                  {s(item.contractor_name)}
                </Link>
              ),
            },
            { key: "nif", label: "NIF" },
            {
              key: "amount",
              label: t("riskAudit.yearAmount"),
              render: (item) => formatCurrency(String(item.amount ?? "")),
            },
          ]}
        />
        <Block
          title={t("riskAudit.reckless")}
          intro={t("riskAudit.recklessIntro")}
          total={d.reckless_bids.total}
          items={d.reckless_bids.items}
          columns={[
            { key: "file_code", label: t("contracts.col.fileCode"), render: contractLink },
            { key: "subject", label: t("contracts.col.subject") },
            {
              key: "drop_pct",
              label: t("riskAudit.drop"),
              render: (item) => <strong>{s(item.drop_pct)}%</strong>,
            },
            {
              key: "award_amount",
              label: t("search.award"),
              render: (item) => formatCurrency(String(item.award_amount ?? "")),
            },
          ]}
        />
        <Block
          title={t("riskAudit.renewals")}
          intro={t("riskAudit.renewalsIntro")}
          total={d.critical_renewals.total}
          items={d.critical_renewals.items}
          columns={[
            { key: "file_code", label: t("contracts.col.fileCode"), render: contractLink },
            { key: "subject", label: t("contracts.col.subject") },
            {
              key: "end_date",
              label: t("contracts.col.end"),
              render: (item) => formatDate(s(item.end_date)),
            },
          ]}
        />
        <Block
          title={t("riskAudit.singleBidder")}
          intro={t("riskAudit.singleBidderIntro")}
          total={d.single_bidder.total}
          items={d.single_bidder.items}
          emptyNote={t("riskAudit.singleBidderEmpty")}
          columns={[
            { key: "file_code", label: t("contracts.col.fileCode"), render: contractLink },
            { key: "subject", label: t("contracts.col.subject") },
            { key: "procedure", label: t("contract.field.procedure") },
          ]}
        />
      </div>
    </div>
  );
}
