import { Link, useParams } from "react-router-dom";

import { Badge, DefinitionList, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { useContracts } from "../contracts/queries";
import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";
import { useContractor } from "./queries";

export function ContractorDetail() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const contractor = useContractor(id);
  const contracts = useContracts({
    "page[size]": 10,
    view: "user",
    "filter[contractor_id]": id,
    sort: "-published_at",
  });

  if (contractor.isPending) return <Skeleton rows={10} />;
  if (contractor.isError || !contractor.data) {
    return <EmptyState icon="🔍" title={t("contractors.notFound")} />;
  }
  const data = contractor.data;

  return (
    <div>
      <nav aria-label="breadcrumb" className="text-sm text-muted">
        <Link to="/contractors" className="text-accent underline-offset-2 hover:underline">
          {t("contractors.title")}
        </Link>
        {" / "}
        <span className="text-ink">{data.name}</span>
      </nav>

      <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
        <PageHeader back backTo="/contractors" title={data.name} />
        <span className="flex gap-1.5">
          {data.third_sector && <Badge tone="accent">{t("contractors.thirdSector")}</Badge>}
        </span>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <SectionCard title={t("contractors.section.company")}>
          <DefinitionList
            items={[
              { label: t("contractors.col.taxId"), value: data.tax_id },
              { label: t("contractors.nationality"), value: data.nationality },
              { label: t("contractors.companyType"), value: data.company_type },
              { label: t("contractors.phone"), value: data.phone },
              { label: t("contractors.email"), value: data.email },
            ]}
          />
        </SectionCard>

        <SectionCard title={t("contractors.section.volume")}>
          <DefinitionList
            items={[
              {
                label: t("contractors.col.contracts"),
                value: `${data.contracts_count} · ${formatCurrency(data.contracts_amount)}`,
              },
              {
                label: t("contractors.col.minors"),
                value: `${data.minor_count} · ${formatCurrency(data.minor_amount)}`,
              },
              { label: t("contractors.col.total"), value: formatCurrency(data.total_amount) },
            ]}
          />
        </SectionCard>

        {(data.aliases ?? []).length > 0 && (
          <SectionCard title={t("contractors.section.aliases")}>
            <ul className="flex flex-wrap gap-2 text-sm">
              {(data.aliases ?? []).map((alias) => (
                <li
                  key={alias}
                  className="rounded-full border border-line bg-surface px-3 py-1 text-muted"
                >
                  {alias}
                </li>
              ))}
            </ul>
          </SectionCard>
        )}
      </div>

      <div className="mt-4">
        <SectionCard title={t("contractors.section.contracts")}>
          {contracts.data?.data.length ? (
            <>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th scope="col" className="py-1 pr-2 font-medium">
                      {t("contracts.col.fileCode")}
                    </th>
                    <th scope="col" className="py-1 pr-2 font-medium">
                      {t("contracts.col.subject")}
                    </th>
                    <th scope="col" className="py-1 pr-2 font-medium">
                      {t("contracts.col.published")}
                    </th>
                    <th scope="col" className="py-1 text-right font-medium">
                      {t("contracts.col.amount")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {contracts.data.data.map((contract) => (
                    <tr key={contract.id} className="border-t border-line">
                      <td className="py-1.5 pr-2 whitespace-nowrap">
                        <Link
                          to={`/contracts/${contract.id}`}
                          className="text-accent underline-offset-2 hover:underline"
                        >
                          {contract.file_code}
                        </Link>
                      </td>
                      <td
                        className="max-w-md truncate py-1.5 pr-2 text-muted"
                        title={contract.subject ?? ""}
                      >
                        {contract.subject ?? "—"}
                      </td>
                      <td className="py-1.5 pr-2 whitespace-nowrap text-muted">
                        {formatDate(contract.published_at)}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">
                        {formatCurrency(contract.award_amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-3 text-sm">
                <Link
                  to={`/contracts?contractor=${id}`}
                  className="text-accent underline-offset-2 hover:underline"
                >
                  {t("contractors.allContracts")} →
                </Link>
              </p>
            </>
          ) : (
            <p className="text-sm text-muted">{t("contractors.noVisibleContracts")}</p>
          )}
        </SectionCard>
      </div>
    </div>
  );
}
