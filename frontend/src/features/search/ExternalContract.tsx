import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import { Badge, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { Globe } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { PhaseFolders, SaveToFolder } from "../../components/PhaseExplorer";
import { CpvChips, CriteriaBars, InfoPair, SheetTabs, Timeline } from "../../components/contractSheet";
import { t } from "../../i18n";
import { formatCurrency, formatDate, formatDuration } from "../../lib/format";
import { phasesFromUrls } from "../../lib/phases";

type Row = Record<string, unknown>;

function text(row: Row, key: string): string | null {
  const value = row[key];
  return typeof value === "string" && value ? value : null;
}

/** Fitxa externa del SuperBuscador (specs/super-search.md): tot el registre
 * públic d'un expedient, només lectura, amb l'estètica de fitxa completa. */
export function ExternalContract() {
  const [params] = useSearchParams();
  const fileCode = params.get("code") ?? "";
  const [tab, setTab] = useState("resum");

  const detail = useQuery({
    queryKey: ["public-contract", fileCode],
    enabled: fileCode.length > 0,
    staleTime: 5 * 60 * 1000,
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.GET("/public-registry/contracts/{file_code}", {
        params: { path: { file_code: fileCode } },
      });
      if (error !== undefined) throw error;
      return data.data as Row[];
    },
  });

  if (!fileCode) return <EmptyState icon="🔎" title={t("search.detailMissingCode")} />;
  if (detail.isPending) return <Skeleton rows={12} />;
  if (detail.isError || !detail.data?.length) {
    return <EmptyState icon="⚠️" title={t("search.detailNotFound")} />;
  }

  const rows = detail.data;
  // La fila més informada com a base (les agregades van per fase/lot).
  const base: Row =
    rows.find((row) => text(row, "formalized_at")) ??
    rows.find((row) => text(row, "award_notice_date")) ??
    rows[0] ??
    {};
  const links = (base.links ?? {}) as Record<string, string>;
  const portal = links.enllac_perfil_contractant ?? links.enllac_publicacio;
  const contractor = (base.contractor ?? {}) as Record<string, unknown>;
  const lots = new Set(rows.map((row) => text(row, "lot") ?? "")).size;
  const mergedPhaseUrls: Record<string, unknown> = {};
  for (const row of rows) {
    for (const [phase, url] of Object.entries((row.phase_urls ?? {}) as Record<string, unknown>)) {
      if (!(phase in mergedPhaseUrls)) mergedPhaseUrls[phase] = url;
    }
  }
  const phases = phasesFromUrls(mergedPhaseUrls);
  const licitacioUrl = phases.find((p) => p.phase === "licitacio")?.url;

  return (
    <div>
      <p className="text-xs text-muted">
        {t("search.fileChip")}{" "}
        <span className="rounded bg-surface-raised px-1.5 py-0.5 font-mono text-ink">
          {fileCode}
        </span>
      </p>
      <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          back
          icon={Globe}
          title={text(base, "subject") ?? fileCode}
          subtitle={[text(base, "awarding_body"), text(base, "awarding_department")]
            .filter(Boolean)
            .join(" · ")}
        />
        <span className="flex items-center gap-3 pt-1">
          {text(base, "status") && <Badge tone="accent">{text(base, "status")}</Badge>}
          <SaveToFolder fileCode={fileCode} />
          {portal && (
            <a href={portal} target="_blank" rel="noreferrer" className="text-xs text-accent underline">
              {t("search.openInPortal")}
            </a>
          )}
        </span>
      </div>

      <div className="mt-4">
        <SheetTabs
          tabs={[
            { key: "resum", label: t("sheet.tabSummary") },
            ...(phases.length > 0 ? [{ key: "documents", label: t("search.documents") }] : []),
            ...(rows.length > 1
              ? [{ key: "lots", label: t("sheet.lotRows"), count: rows.length }]
              : []),
          ]}
          active={tab}
          onSelect={setTab}
        />
      </div>

      {tab === "resum" && (
      <>
      <div className="mt-5 grid gap-4 lg:grid-cols-[290px_1fr]">
        <div className="space-y-4">
          <SectionCard title={t("sheet.timeline")}>
            <Timeline
              events={[
                { label: t("contract.field.priorNotice"), date: text(base, "prior_notice_date") },
                { label: t("contract.field.published"), date: text(base, "published_at") },
                { label: t("sheet.tenderNotice"), date: text(base, "tender_notice_date") },
                { label: t("sheet.awardNotice"), date: text(base, "award_notice_date") },
                {
                  label: t("contract.field.formalized"),
                  date: text(base, "formalization_notice_date") ?? text(base, "formalized_at"),
                },
                { label: t("contract.field.end"), date: text(base, "end_date") },
              ].filter((event, index) => event.date || index >= 2)}
            />
          </SectionCard>
          <SectionCard title={t("sheet.cpvs")}>
            <CpvChips code={text(base, "cpv_code")} description={text(base, "cpv_description")} />
          </SectionCard>
        </div>

        <SectionCard title={t("sheet.relevantInfo")}>
          {text(base, "subject") && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-accent">
                {t("sheet.object")}
              </h4>
              <p className="mt-1 text-sm text-ink">{text(base, "subject")}</p>
            </div>
          )}
          <div className="grid gap-x-8 sm:grid-cols-2">
            <div>
              <h4 className="mt-2 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("sheet.general")}
              </h4>
              <InfoPair label={t("contract.field.status")} value={text(base, "status")} />
              <InfoPair label={t("contract.field.procedure")} value={text(base, "procedure")} />
              <InfoPair label={t("contract.field.type")} value={text(base, "contract_type")} />
              <InfoPair label={t("contract.field.processing")} value={text(base, "processing_type")} />
              <InfoPair label={t("sheet.lots")} value={lots > 1 ? lots : lots === 1 ? 1 : "—"} />
              <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("contract.section.dates")}
              </h4>
              <InfoPair
                label={t("contract.field.duration")}
                value={formatDuration(base.duration_months as number | null)}
              />
              <InfoPair label={t("contract.field.start")} value={formatDate(text(base, "start_date"))} />
              <InfoPair label={t("contract.field.end")} value={formatDate(text(base, "end_date"))} />
              <InfoPair
                label={t("contract.field.formalized")}
                value={formatDate(text(base, "formalized_at"))}
              />
            </div>
            <div>
              <h4 className="mt-2 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("contract.section.amounts")}
              </h4>
              <InfoPair
                label={t("search.budget")}
                value={formatCurrency(base.budget_vat as string | null)}
              />
              <InfoPair
                label={t("contract.field.budgetNoVat")}
                value={formatCurrency(base.budget_no_vat as string | null)}
              />
              <InfoPair
                label={t("sheet.estimatedValue")}
                value={formatCurrency(
                  (base.estimated_value ?? base.tender_amount) as string | null,
                )}
              />
              <InfoPair
                label={t("search.award")}
                value={formatCurrency(base.award_amount as string | null)}
              />
              <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("search.contractor")}
              </h4>
              <InfoPair
                label={t("contracts.col.contractor")}
                value={typeof contractor.name === "string" ? contractor.name : "—"}
              />
              <InfoPair
                label={t("contract.field.nif")}
                value={typeof contractor.tax_id === "string" ? contractor.tax_id : "—"}
              />
            </div>
          </div>
        </SectionCard>
      </div>

      {licitacioUrl && <CriteriaSection url={licitacioUrl} />}
      <div className="mt-4">
        <SectionCard title={t("sheet.awardingBody")}>
          <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
            <InfoPair label={t("sheet.organisme")} value={text(base, "awarding_body")} />
            <InfoPair
              label={t("contract.field.awardingDepartment")}
              value={text(base, "awarding_department")}
            />
            <InfoPair label="DIR3" value={text(base, "dir3_code")} />
            <InfoPair label="INE10" value={text(base, "ine10_code")} />
            <InfoPair label="NUTS" value={text(base, "nuts_code")} />
            <InfoPair
              label="Web"
              value={
                portal ? (
                  <a href={portal} target="_blank" rel="noreferrer" className="text-accent underline">
                    {t("search.openInPortal")}
                  </a>
                ) : (
                  "—"
                )
              }
            />
          </div>
        </SectionCard>
      </div>
      </>
      )}

      {tab === "documents" && phases.length > 0 && (
        <div className="mt-4">
          <SectionCard title={t("search.documents")}>
            <PhaseFolders phases={phases} fileCode={fileCode} />
          </SectionCard>
        </div>
      )}

      {tab === "lots" && rows.length > 1 && (
        <div className="mt-4">
          <SectionCard title={`${t("sheet.lotRows")} (${rows.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th scope="col" className="py-1 pr-2 font-medium">{t("contracts.col.state")}</th>
                    <th scope="col" className="py-1 pr-2 font-medium">Lot</th>
                    <th scope="col" className="py-1 pr-2 font-medium">{t("search.budget")}</th>
                    <th scope="col" className="py-1 pr-2 font-medium">{t("search.award")}</th>
                    <th scope="col" className="py-1 font-medium">{t("search.contractor")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => {
                    const rowContractor = (row.contractor ?? {}) as Record<string, unknown>;
                    return (
                      <tr key={index} className="border-t border-line">
                        <td className="py-1.5 pr-2">{text(row, "status") ?? "—"}</td>
                        <td className="py-1.5 pr-2">{text(row, "lot") || "—"}</td>
                        <td className="py-1.5 pr-2 tabular-nums">
                          {formatCurrency(row.budget_vat as string | null)}
                        </td>
                        <td className="py-1.5 pr-2 tabular-nums">
                          {formatCurrency(row.award_amount as string | null)}
                        </td>
                        <td className="py-1.5">
                          {typeof rowContractor.name === "string" ? rowContractor.name : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>
      )}

    </div>
  );
}

function CriteriaSection(props: { url: string }) {
  const phase = useQuery({
    queryKey: ["public-phase", props.url],
    staleTime: 10 * 60 * 1000,
    queryFn: async () => {
      const { data, error } = await api.GET("/public-registry/phase", {
        params: { query: { url: props.url } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  const criteria = phase.data?.criteria ?? [];
  if (phase.isPending || criteria.length === 0) return null;
  return (
    <div className="mt-4">
      <SectionCard title={t("search.criteria")}>
        <CriteriaBars
          criteria={criteria.map((criterion) => ({
            name: String(criterion.name ?? "—"),
            weight: (criterion.weight ?? null) as number | null,
          }))}
        />
      </SectionCard>
    </div>
  );
}
