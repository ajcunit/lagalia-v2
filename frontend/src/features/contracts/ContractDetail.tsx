import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { components } from "../../api/generated/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, DefinitionList, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { Markdown } from "../../components/Markdown";
import { PageHeader } from "../../components/PageHeader";
import { CpvChips, CriteriaBars, InfoPair, SheetTabs, Timeline } from "../../components/contractSheet";
import { FileTypeIcon } from "../../components/FileTypeIcon";
import { t } from "../../i18n";
import { streamNdjson } from "../../lib/stream";
import { ca } from "../../i18n/ca";
import {
  formatBytes,
  formatCurrency,
  formatDate,
  formatDateTime,
  formatDuration,
} from "../../lib/format";
import { Folder, FolderOpen, Scale } from "lucide-react";

import { ContractTasks } from "../tasks/ContractTasks";
import {
  useContract,
  useContractCommittee,
  useContractCriteria,
  useContractDocuments,
  useContractExtensions,
  useContractHistory,
  useContractModifications,
  useDismissExpiry,
  useEnrichContract,
  useFinishContract,
  useJobStatus,
} from "./queries";

function yesNo(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value ? t("common.yes") : t("common.no");
}

function phaseLabel(phase: string): string {
  const key = `contract.phase.${phase}`;
  return key in ca ? ca[key as keyof typeof ca] : phase;
}

type PhaseDoc = components["schemas"]["PhaseDocument"];

/** Documents del repositori amb revisió legal en streaming (specs/legal-corpus.md). */
function DocumentsSection(props: { documents: PhaseDoc[]; canReview: boolean }) {
  const [reviewing, setReviewing] = useState<{ id: number; title: string } | null>(null);
  const [reviewText, setReviewText] = useState("");
  const [articles, setArticles] = useState<{ article?: string; url?: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const review = useMutation({
    mutationFn: async (doc: PhaseDoc) => {
      setReviewing({ id: doc.id, title: doc.title ?? String(doc.id) });
      setReviewText("");
      setArticles([]);
      setError(null);
      await streamNdjson(`/compliance/documents/${doc.id}/review/stream`, {}, (event) => {
        if (event.type === "articles")
          setArticles(event.articles as { article?: string; url?: string }[]);
        if (event.type === "delta") setReviewText((prev) => prev + String(event.text ?? ""));
        if (event.type === "error") setError(String(event.detail ?? ""));
      });
    },
    onError: (err: Error) => {
      setError(
        err.message.includes("409")
          ? t("contract.documents.reviewNoCopy")
          : t("contract.documents.reviewError"),
      );
    },
  });

  // Carpetes per fase (mateixa metàfora que la fitxa externa).
  const groups = new Map<string, PhaseDoc[]>();
  for (const doc of props.documents) {
    const list = groups.get(doc.phase) ?? [];
    list.push(doc);
    groups.set(doc.phase, list);
  }
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>({});

  return (
    <SectionCard title={`${t("contract.section.documents")} (${props.documents.length})`}>
      <ul className="space-y-2">
        {[...groups.entries()].map(([phase, docs]) => {
          const open = openFolders[phase] ?? groups.size === 1;
          return (
            <li key={phase} className="rounded-md border border-line bg-surface">
              <button
                type="button"
                aria-expanded={open}
                onClick={() => setOpenFolders({ ...openFolders, [phase]: !open })}
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium text-ink hover:bg-accent-soft"
              >
                <span aria-hidden>
                  {open ? (
                    <FolderOpen className="h-4 w-4 text-accent" />
                  ) : (
                    <Folder className="h-4 w-4 text-muted" />
                  )}
                </span>
                {phaseLabel(phase)}
                <span className="text-xs font-normal text-muted">({docs.length})</span>
              </button>
              {open && (
                <table className="w-full border-t border-line text-sm">
                  <tbody>
                    {docs.map((doc) => (
                      <tr key={doc.id} className="border-t border-line first:border-t-0">
                        <td className="py-1.5 pl-3 pr-2">
                          <FileTypeIcon
                            name={doc.title}
                            className="mr-1.5 inline h-4 w-4 -translate-y-px"
                          />
                          {doc.download_url ? (
                            <a
                              href={doc.download_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-accent underline-offset-2 hover:underline"
                              aria-label={`${doc.title ?? ""} — ${t("contract.documents.open")}`}
                            >
                              {doc.title ?? "—"} ↗
                            </a>
                          ) : (
                            (doc.title ?? "—")
                          )}
                        </td>
                        <td className="py-1.5 pr-2 text-right tabular-nums text-muted">
                          {formatBytes(doc.size)}
                        </td>
                        {props.canReview && (
                          <td className="w-32 py-1.5 pl-2 pr-3 text-right">
                            {doc.has_copy ? (
                              <button
                                type="button"
                                disabled={review.isPending}
                                className="text-xs text-accent underline-offset-2 hover:underline disabled:opacity-50"
                                onClick={() => review.mutate(doc)}
                              >
                                <Scale className="mr-1 inline h-3 w-3 -translate-y-px" aria-hidden />
                                {t("contract.documents.review")}
                              </button>
                            ) : (
                              <span
                                className="text-xs text-muted"
                                title={t("contract.documents.reviewNoCopy")}
                              >
                                —
                              </span>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </li>
          );
        })}
      </ul>

      {reviewing && (
        <div className="mt-3 rounded-lg border border-accent/40 bg-surface p-3">
          <div className="flex items-start justify-between gap-2">
            <h4 className="text-sm font-semibold text-ink">
              {t("docgen.legalTitle")} — {reviewing.title}
            </h4>
            <button
              type="button"
              className="text-xs text-muted underline"
              onClick={() => {
                setReviewing(null);
                setReviewText("");
                setError(null);
              }}
            >
              {t("contract.documents.reviewClose")}
            </button>
          </div>
          {articles.length > 0 && (
            <p className="mt-1 text-xs text-muted">
              {t("docgen.legalArticles")}:{" "}
              {articles.map((a) => a.article).filter(Boolean).join(" · ")}
            </p>
          )}
          {error ? (
            <p className="mt-2 text-sm text-danger">{error}</p>
          ) : reviewText ? (
            <div className="mt-2 max-h-96 overflow-auto rounded-md bg-surface-raised p-3">
              <Markdown>{reviewText}</Markdown>
              {review.isPending && <span className="animate-pulse text-muted">▍</span>}
            </div>
          ) : (
            <p className="mt-2 animate-pulse text-sm text-muted">{t("docgen.reviewing")}</p>
          )}
          <p className="mt-1 text-xs text-muted">{t("docgen.legalDisclaimer")}</p>
        </div>
      )}
    </SectionCard>
  );
}

export function ContractDetail() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const contract = useContract(id);
  const extensions = useContractExtensions(id);
  const modifications = useContractModifications(id);
  const history = useContractHistory(id);
  const criteria = useContractCriteria(id);
  const committee = useContractCommittee(id);
  const documents = useContractDocuments(id);
  const finish = useFinishContract(id);
  const dismiss = useDismissExpiry(id);
  const enrich = useEnrichContract(id);
  const { permissions } = useAuth();
  const actions = permissions?.actions ?? [];
  const [tab, setTab] = useState("resum");

  // Seguiment del job d'enriquiment fins a estat terminal (B-012, v. sondeig).
  const [enrichJobId, setEnrichJobId] = useState<string | null>(null);
  const enrichJob = useJobStatus(enrichJobId);
  const jobStatus = enrichJob.data?.status;
  const queryClient = useQueryClient();
  useEffect(() => {
    if (jobStatus === "success") {
      setEnrichJobId(null);
      void queryClient.invalidateQueries({ queryKey: ["contract", id] });
      void queryClient.invalidateQueries({ queryKey: ["contract-criteria", id] });
      void queryClient.invalidateQueries({ queryKey: ["contract-committee", id] });
      void queryClient.invalidateQueries({ queryKey: ["contract-documents", id] });
    }
  }, [jobStatus, id, queryClient]);

  if (contract.isPending) return <Skeleton rows={12} />;
  if (contract.isError || !contract.data) {
    return <EmptyState icon="🔒" title={t("contract.notFound")} />;
  }
  const data = contract.data;

  const canCloseAlert = actions.includes("contracts:close_alert");
  const canEnrich = actions.includes("contracts:enrich");

  const onFinish = () => {
    if (window.confirm(t("contract.action.finishConfirm"))) finish.mutate();
  };
  const onDismiss = () => {
    if (window.confirm(t("contract.action.dismissConfirm"))) dismiss.mutate();
  };
  const onEnrich = () => {
    enrich.mutate(undefined, {
      onSuccess: (job) => setEnrichJobId(job.id),
      onError: (error) =>
        window.alert(t("contract.action.error", { message: String(error) })),
    });
  };
  const enriching = enrich.isPending || jobStatus === "queued" || jobStatus === "running";

  return (
    <div>
      <nav aria-label="breadcrumb" className="text-sm text-muted">
        <Link to="/contracts" className="text-accent underline-offset-2 hover:underline">
          {t("contracts.title")}
        </Link>
        {" / "}
        <span className="text-ink">{data.file_code}</span>
      </nav>

      <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          back
          backTo="/contracts"
          title={`${data.file_code}${data.lot ? ` · lot ${data.lot}` : ""}`}
          subtitle={data.subject ?? undefined}
        />
        <span className="flex items-center gap-1.5">
          {canEnrich && data.phase_urls && Object.keys(data.phase_urls).length > 0 && (
            <Button onClick={onEnrich} disabled={enriching}>
              {enriching ? t("contract.action.enriching") : t("contract.action.enrich")}
            </Button>
          )}
          {data.expiry_warning && <Badge tone="warning">{t("contracts.badge.expiry")}</Badge>}
          {data.possibly_finished && (
            <Badge tone="danger">{t("contracts.badge.finished")}</Badge>
          )}
          <Badge tone="accent">{data.status}</Badge>
        </span>
      </div>

      {jobStatus === "failed" && (
        <div
          role="alert"
          className="mt-4 rounded-md border border-danger/40 bg-danger/10 p-3 text-sm text-ink"
        >
          {t("contract.action.enrichFailed", {
            message: enrichJob.data?.error ?? "error desconegut",
          })}
        </div>
      )}

      {data.possibly_finished && (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-danger/40 bg-danger/10 p-3 text-sm text-ink"
        >
          <span>{t("contract.alert.possiblyFinished")}</span>
          {canCloseAlert && (
            <span className="flex gap-2">
              <Button tone="danger" onClick={onFinish} disabled={finish.isPending}>
                {t("contract.action.finish")}
              </Button>
              <Button onClick={onDismiss} disabled={dismiss.isPending}>
                {t("contract.action.dismiss")}
              </Button>
            </span>
          )}
        </div>
      )}
      {!data.possibly_finished && data.expiry_warning && (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-warning/40 bg-warning/10 p-3 text-sm text-ink"
        >
          <span>{t("contract.alert.expiring")}</span>
          {canCloseAlert && (
            <Button onClick={onDismiss} disabled={dismiss.isPending}>
              {t("contract.action.dismiss")}
            </Button>
          )}
        </div>
      )}

      <div className="mt-5">
        <SheetTabs
          tabs={[
            { key: "resum", label: t("sheet.tabSummary") },
            { key: "documents", label: t("contract.section.documents"), count: documents.data?.data.length ?? 0 },
            {
              key: "execucio",
              label: t("sheet.tabExecution"),
              count: data.counters.extensions + data.counters.modifications,
            },
            { key: "historial", label: t("sheet.tabHistory"), count: data.counters.history },
            { key: "tasques", label: t("sheet.tabTasks") },
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
                { label: t("contract.field.priorNotice"), date: data.prior_notice_date },
                { label: t("contract.field.published"), date: data.published_at },
                { label: t("sheet.tenderNotice"), date: data.tender_notice_date },
                { label: t("sheet.awardNotice"), date: data.award_notice_date },
                {
                  label: t("contract.field.formalized"),
                  date: data.formalization_notice_date ?? data.formalized_at,
                },
                { label: t("contract.field.start"), date: data.start_date },
                {
                  label: t("contract.field.calculatedEnd"),
                  date: data.calculated_end_date ?? data.end_date,
                },
              ].filter((event, index) => event.date || index >= 1)}
            />
          </SectionCard>
          <SectionCard title={t("sheet.cpvs")}>
            <CpvChips code={data.cpv_code} description={data.cpv_description} />
          </SectionCard>
        </div>

        <SectionCard title={t("sheet.relevantInfo")}>
          {data.subject && (
            <div className="mb-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-accent">
                {t("sheet.object")}
              </h4>
              <p className="mt-1 text-sm text-ink">{data.subject}</p>
            </div>
          )}
          <div className="grid gap-x-8 sm:grid-cols-2">
            <div>
              <h4 className="mt-2 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("sheet.general")}
              </h4>
              <InfoPair label={t("contract.field.status")} value={data.status} />
              <InfoPair
                label={t("contract.field.internalStatus")}
                value={data.internal_status}
              />
              <InfoPair label={t("contract.field.procedure")} value={data.procedure} />
              <InfoPair label={t("contract.field.type")} value={data.contract_type} />
              <InfoPair label={t("contract.field.processing")} value={data.processing_type} />
              <InfoPair label={t("contract.field.source")} value={data.source} />
              <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("contract.section.dates")}
              </h4>
              <InfoPair
                label={t("contract.field.duration")}
                value={formatDuration(data.duration_months)}
              />
              <InfoPair label={t("contract.field.start")} value={formatDate(data.start_date)} />
              <InfoPair label={t("contract.field.end")} value={formatDate(data.end_date)} />
              <InfoPair
                label={t("contract.field.calculatedEnd")}
                value={formatDate(data.calculated_end_date)}
              />
              <InfoPair
                label={t("contract.field.warningOverride")}
                value={data.warning_months_override ?? "—"}
              />
            </div>
            <div>
              <h4 className="mt-2 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("contract.section.amounts")}
              </h4>
              <InfoPair
                label={t("contract.field.budgetVat")}
                value={formatCurrency(data.budget_vat)}
              />
              <InfoPair
                label={t("contract.field.budgetNoVat")}
                value={formatCurrency(data.budget_no_vat)}
              />
              <InfoPair
                label={t("contract.field.tender")}
                value={formatCurrency(data.tender_amount)}
              />
              <InfoPair
                label={t("contract.field.award")}
                value={formatCurrency(data.award_amount)}
              />
              <InfoPair
                label={t("contract.field.awardVat")}
                value={formatCurrency(data.award_amount_vat)}
              />
              <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("contract.section.contractor")}
              </h4>
              <InfoPair
                label={t("contracts.col.contractor")}
                value={data.contractor?.name ?? "—"}
              />
              <InfoPair label={t("contract.field.nif")} value={data.contractor?.tax_id ?? "—"} />
              <h4 className="mt-4 text-xs font-semibold uppercase tracking-wide text-accent">
                {t("contract.section.classification")}
              </h4>
              <InfoPair
                label={t("contract.field.nuts")}
                value={
                  data.nuts_code
                    ? `${data.nuts_code}${data.nuts_description ? ` — ${data.nuts_description}` : ""}`
                    : "—"
                }
              />
              <InfoPair label={t("contract.field.financing")} value={data.financing} />
              <InfoPair label={t("contract.field.awardingBody")} value={data.awarding_body} />
              <InfoPair
                label={t("contract.field.awardingDepartment")}
                value={data.awarding_department}
              />
            </div>
          </div>
        </SectionCard>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <SectionCard title={t("contract.section.tender")}>
          {data.enriched_at ? (
            <DefinitionList
              items={[
                {
                  label: t("contract.field.receivedOffers"),
                  value: data.received_offers ?? "—",
                },
                { label: t("contract.field.harmonized"), value: yesNo(data.is_harmonized) },
                {
                  label: t("contract.field.allowsExtensions"),
                  value: yesNo(data.allows_extensions),
                },
                {
                  label: t("contract.field.allowsModifications"),
                  value: yesNo(data.allows_modifications),
                },
                {
                  label: t("contract.field.socialReserve"),
                  value: yesNo(data.social_reserve),
                },
                {
                  label: t("contract.field.subcontracting"),
                  value: yesNo(data.subcontracting_allowed),
                },
              ]}
            />
          ) : (
            <p className="text-sm text-muted">{t("contract.enrichmentPending")}</p>
          )}
        </SectionCard>

        {(criteria.data?.data.length ?? 0) > 0 && (
          <SectionCard title={t("contract.section.criteria")}>
            <CriteriaBars
              criteria={(criteria.data?.data ?? []).map((criterion) => ({
                name: criterion.name ?? "—",
                weight: criterion.weight,
              }))}
            />
          </SectionCard>
        )}

        {(committee.data?.data.length ?? 0) > 0 && (
          <SectionCard title={t("contract.section.committee")}>
            <ul className="space-y-1.5 text-sm">
              {committee.data?.data.map((member) => (
                <li
                  key={member.id}
                  className="flex justify-between gap-2 border-t border-line pt-1.5 first:border-0"
                >
                  <span className="text-ink">
                    {[member.first_name, member.last_name].filter(Boolean).join(" ") || "—"}
                  </span>
                  <span className="text-right text-muted">{member.role ?? ""}</span>
                </li>
              ))}
            </ul>
          </SectionCard>
        )}

        {data.links && Object.keys(data.links).length > 0 && (
          <SectionCard title={t("contract.section.links")}>
            <ul className="space-y-1 text-sm">
              {Object.entries(data.links).map(([key, url]) => (
                <li key={key}>
                  <a
                    href={String(url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent underline-offset-2 hover:underline"
                  >
                    {key} ↗
                  </a>
                </li>
              ))}
            </ul>
          </SectionCard>
        )}
      </div>

      {(data.siblings ?? []).length > 0 && (
        <div className="mt-4">
          <SectionCard title={t("contract.section.siblings")}>
            <ul className="divide-y divide-line text-sm">
              {(data.siblings ?? []).map((sibling) => (
                <li key={sibling.id} className="flex items-center justify-between py-2">
                  <Link
                    to={`/contracts/${sibling.id}`}
                    className="text-accent underline-offset-2 hover:underline"
                  >
                    {sibling.file_code}
                    {sibling.lot ? ` · lot ${sibling.lot}` : ""} — {sibling.status}
                  </Link>
                  <span className="tabular-nums text-muted">
                    {formatCurrency(sibling.award_amount)}
                  </span>
                </li>
              ))}
            </ul>
          </SectionCard>
        </div>
      )}

      </>
      )}

      {tab === "tasques" && (
        <div className="mt-4">
          <ContractTasks contractId={id} />
        </div>
      )}

      {tab === "documents" && (documents.data?.data.length ?? 0) > 0 && (
        <div className="mt-4">
          <DocumentsSection
            documents={documents.data?.data ?? []}
            canReview={actions.includes("compliance:run")}
          />
        </div>
      )}

      {tab === "execucio" && (
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <SectionCard title={`${t("contract.section.extensions")} (${data.counters.extensions})`}>
          {extensions.data?.data.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contract.extension.number")}
                  </th>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contract.extension.period")}
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    {t("contract.extension.amount")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {extensions.data.data.map((extension) => (
                  <tr key={extension.id} className="border-t border-line">
                    <td className="py-1.5 pr-2 tabular-nums">{extension.number}</td>
                    <td className="py-1.5 pr-2 text-muted">
                      {formatDate(extension.start_date)} → {formatDate(extension.end_date)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">
                      {formatCurrency(extension.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted">{t("contract.extensions.empty")}</p>
          )}
        </SectionCard>

        <SectionCard
          title={`${t("contract.section.modifications")} (${data.counters.modifications})`}
        >
          {modifications.data?.data.length ? (
            <ul className="space-y-1.5 text-sm">
              {modifications.data.data.map((modification) => (
                <li key={modification.id} className="flex justify-between border-t border-line pt-1.5 first:border-0">
                  <span className="text-muted">
                    #{modification.number} · {formatDate(modification.approved_at)}
                  </span>
                  <span className="tabular-nums">{formatCurrency(modification.amount)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("contract.modifications.empty")}</p>
          )}
        </SectionCard>
      </div>

      )}

      {tab === "historial" && (
      <div className="mt-4">
        <SectionCard title={`${t("contract.section.history")} (${data.counters.history})`}>
          {history.data?.data.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contract.history.when")}
                  </th>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contract.history.field")}
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    {t("contract.history.change")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {history.data.data.map((entry) => (
                  <tr key={entry.id} className="border-t border-line align-top">
                    <td className="py-1.5 pr-2 whitespace-nowrap text-muted">
                      {formatDateTime(entry.changed_at)}
                      <Badge tone="neutral">{entry.change_type}</Badge>
                    </td>
                    <td className="py-1.5 pr-2 font-medium text-ink">{entry.field}</td>
                    <td className="py-1.5 text-muted">
                      <span className="line-through">{entry.old_value ?? "∅"}</span>{" "}
                      <span className="text-ink">{entry.new_value ?? "∅"}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted">{t("contract.history.empty")}</p>
          )}
        </SectionCard>
      </div>
      )}
    </div>
  );
}
