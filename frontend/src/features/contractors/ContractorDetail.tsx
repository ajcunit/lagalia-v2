import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Contact, Info, TrendingUp } from "lucide-react";

import { api } from "../../api/client";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, DefinitionList, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { useContracts } from "../contracts/queries";
import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";
import { useContractor } from "./queries";
import { SheetTabs } from "../../components/contractSheet";

export function ContractorDetail() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const contractor = useContractor(id);
  const [tab, setTab] = useState("resum");
  const { permissions } = useAuth();
  // Qui pot canviar de vista (admin/gestor) veu TOTS els contractes de
  // l'adjudicatari; la resta, el seu abast departamental.
  const view = permissions?.can_switch_view ? ("all" as const) : ("user" as const);
  const contracts = useContracts({
    "page[size]": 10,
    view,
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

      <div className="mt-4">
        <SheetTabs
          tabs={[
            { key: "resum", label: t("sheet.tabSummary"), icon: Info },
            { key: "contacte", label: t("contractors.tabContact"), icon: Contact },
            ...(data.tax_id
              ? [{ key: "analisi", label: t("contractors.tabAnalysis"), icon: TrendingUp }]
              : []),
          ]}
          active={tab}
          onSelect={setTab}
        />
      </div>

      {tab === "contacte" && (
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
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
      )}

      {tab === "resum" && (
      <>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
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

      </div>

      <div className="mt-4">
        <SectionCard
          title={
            view === "all"
              ? t("contractors.section.contractsAll")
              : t("contractors.section.contracts")
          }
        >
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
            <p className="text-sm text-muted">
              {view === "all"
                ? t("contractors.noContracts")
                : t("contractors.noVisibleContracts")}
            </p>
          )}
        </SectionCard>
      </div>
      </>
      )}

      {tab === "analisi" && data.tax_id && <MarketAnalysis taxId={data.tax_id} />}
    </div>
  );
}

/** Anàlisi de mercat sobre TOT el dataset obert (specs/contractors-ui.md):
 * amb quines administracions treballa, rànquing i mitjanes. Només lectura. */
function MarketAnalysis(props: { taxId: string }) {
  const analysis = useQuery({
    queryKey: ["contractor-analysis", props.taxId],
    staleTime: 10 * 60 * 1000,
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.GET("/public-registry/contractor-analysis", {
        params: { query: { tax_id: props.taxId } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  if (analysis.isPending) {
    return (
      <div className="mt-5">
        <Skeleton rows={8} />
        <p className="mt-2 animate-pulse text-sm text-muted">{t("contractors.analysisLoading")}</p>
      </div>
    );
  }
  if (analysis.isError) {
    return (
      <div className="mt-5">
        <EmptyState icon="⚠️" title={t("contractors.analysisError")} />
      </div>
    );
  }

  const totals = analysis.data.totals as Record<string, string | undefined>;
  const organs = analysis.data.by_organ as Record<string, string | undefined>[];
  const types = analysis.data.by_type as Record<string, string | undefined>[];
  const kpis = [
    { label: t("contractors.kpiFiles"), value: totals.expedients ?? "—" },
    { label: t("contractors.kpiFormalized"), value: totals.expedients_formalitzats ?? "—" },
    { label: t("contractors.kpiOrgans"), value: totals.organs ?? "—" },
    { label: t("contractors.kpiTotal"), value: formatCurrency(totals.import_total ?? null) },
    { label: t("contractors.kpiAvg"), value: formatCurrency(totals.import_mitja ?? null) },
    {
      label: t("contractors.kpiSpan"),
      value:
        totals.primera && totals.darrera
          ? `${formatDate(totals.primera)} — ${formatDate(totals.darrera)}`
          : "—",
    },
  ];

  return (
    <div className="mt-5 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="rounded-lg border border-line bg-surface-raised p-3 shadow-card"
          >
            <p className="text-xs text-muted">{kpi.label}</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-ink">{kpi.value}</p>
          </div>
        ))}
      </div>

      <SectionCard title={t("contractors.organRanking")}>
        {organs.length === 0 ? (
          <p className="text-sm text-muted">{t("contractors.analysisEmpty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="py-1 pr-2 font-medium">#</th>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contractors.colOrgan")}
                  </th>
                  <th scope="col" className="py-1 pr-2 text-right font-medium">
                    {t("contractors.colFiles")}
                  </th>
                  <th scope="col" className="py-1 pr-2 text-right font-medium">
                    {t("contractors.colFormalized")}
                  </th>
                  <th scope="col" className="py-1 pr-2 text-right font-medium">
                    {t("contractors.colTotal")}
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    {t("contractors.colAvg")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {organs.map((row, index) => (
                  <OrganRow
                    key={index}
                    index={index}
                    row={row}
                    taxId={props.taxId}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title={t("contractors.typeBreakdown")}>
        {types.length === 0 ? (
          <p className="text-sm text-muted">{t("contractors.analysisEmpty")}</p>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {types.map((row, index) => (
                <tr key={index} className="border-t border-line first:border-t-0">
                  <td className="py-1.5 pr-2">{row.tipus_contracte ?? "—"}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-muted">
                    {row.expedients ?? "—"} {t("contractors.filesSuffix")}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">
                    {formatCurrency(row.import_total ?? null)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SectionCard>

      <p className="text-xs text-muted">{t("contractors.analysisNote")}</p>
    </div>
  );
}

/** Fila del rànquing amb desplegable: els expedients de l'adjudicatari amb
 * aquella administració, enllaçats a la fitxa externa del SuperBuscador. */
function OrganRow(props: {
  index: number;
  row: Record<string, string | undefined>;
  taxId: string;
}) {
  const [open, setOpen] = useState(false);
  const organ = props.row.nom_organ ?? "";
  const files = useQuery({
    queryKey: ["contractor-organ-files", props.taxId, organ],
    enabled: open && organ.length > 0,
    staleTime: 10 * 60 * 1000,
    queryFn: async () => {
      const { data, error } = await api.GET("/public-registry/search", {
        params: {
          query: {
            "filter[contractor_nif]": props.taxId,
            "filter[organisme]": organ,
            page_size: 50,
          },
        },
      });
      if (error !== undefined) throw error;
      return data.data;
    },
  });

  return (
    <>
      <tr className="border-t border-line">
        <td className="py-1.5 pr-2 tabular-nums text-muted">{props.index + 1}</td>
        <td className="py-1.5 pr-2">
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="text-left text-accent underline-offset-2 hover:underline"
          >
            {open ? "▾" : "▸"} {organ || "—"}
          </button>
        </td>
        <td className="py-1.5 pr-2 text-right tabular-nums">{props.row.expedients ?? "—"}</td>
        <td className="py-1.5 pr-2 text-right tabular-nums">
          {props.row.expedients_formalitzats ?? "0"}
        </td>
        <td className="py-1.5 pr-2 text-right tabular-nums">
          {formatCurrency(props.row.import_total ?? null)}
        </td>
        <td className="py-1.5 text-right tabular-nums">
          {formatCurrency(props.row.import_mitja ?? null)}
        </td>
      </tr>
      {open && (
        <tr className="border-t border-line/60">
          <td />
          <td colSpan={5} className="py-2 pr-2">
            {files.isPending ? (
              <Skeleton rows={2} />
            ) : files.isError ? (
              <p className="text-xs text-danger">{t("contractors.analysisError")}</p>
            ) : (files.data ?? []).length === 0 ? (
              <p className="text-xs text-muted">{t("contractors.analysisEmpty")}</p>
            ) : (
              <ul className="space-y-1 rounded-md bg-surface p-2">
                {(files.data ?? []).map((card, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2 text-xs">
                    <Link
                      to={`/search/detail?code=${encodeURIComponent(card.file_code)}`}
                      className="font-mono text-accent underline-offset-2 hover:underline"
                    >
                      {card.file_code}
                    </Link>
                    <span className="min-w-0 flex-1 truncate text-ink" title={card.subject ?? ""}>
                      {card.subject ?? "—"}
                    </span>
                    <Badge tone="neutral">{card.status}</Badge>
                    <span className="tabular-nums text-muted">
                      {formatCurrency(card.award_amount ?? card.budget_vat ?? null)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
