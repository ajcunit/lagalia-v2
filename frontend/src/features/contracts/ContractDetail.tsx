import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, DefinitionList, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { ca } from "../../i18n/ca";
import {
  formatBytes,
  formatCurrency,
  formatDate,
  formatDateTime,
  formatDuration,
} from "../../lib/format";
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
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">
            {data.file_code}
            {data.lot && <span className="ml-2 text-base text-muted">lot {data.lot}</span>}
          </h1>
          <p className="mt-1 max-w-3xl text-muted">{data.subject}</p>
        </div>
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

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <SectionCard title={t("contract.section.overview")}>
          <DefinitionList
            items={[
              { label: t("contract.field.status"), value: data.status },
              { label: t("contract.field.internalStatus"), value: data.internal_status },
              { label: t("contract.field.type"), value: data.contract_type },
              { label: t("contract.field.procedure"), value: data.procedure },
              { label: t("contract.field.processing"), value: data.processing_type },
              { label: t("contract.field.awardingBody"), value: data.awarding_body },
              {
                label: t("contract.field.awardingDepartment"),
                value: data.awarding_department,
              },
              { label: t("contract.field.source"), value: data.source },
            ]}
          />
        </SectionCard>

        <SectionCard title={t("contract.section.amounts")}>
          <DefinitionList
            items={[
              { label: t("contract.field.tender"), value: formatCurrency(data.tender_amount) },
              { label: t("contract.field.award"), value: formatCurrency(data.award_amount) },
              {
                label: t("contract.field.awardVat"),
                value: formatCurrency(data.award_amount_vat),
              },
              {
                label: t("contract.field.budgetNoVat"),
                value: formatCurrency(data.budget_no_vat),
              },
              { label: t("contract.field.budgetVat"), value: formatCurrency(data.budget_vat) },
            ]}
          />
        </SectionCard>

        <SectionCard title={t("contract.section.dates")}>
          <DefinitionList
            items={[
              { label: t("contract.field.published"), value: formatDate(data.published_at) },
              { label: t("contract.field.formalized"), value: formatDate(data.formalized_at) },
              { label: t("contract.field.start"), value: formatDate(data.start_date) },
              { label: t("contract.field.end"), value: formatDate(data.end_date) },
              {
                label: t("contract.field.calculatedEnd"),
                value: formatDate(data.calculated_end_date),
              },
              {
                label: t("contract.field.duration"),
                value: formatDuration(data.duration_months),
              },
              {
                label: t("contract.field.warningOverride"),
                value: data.warning_months_override ?? "—",
              },
            ]}
          />
        </SectionCard>

        <SectionCard title={t("contract.section.contractor")}>
          <DefinitionList
            items={[
              {
                label: t("contracts.col.contractor"),
                value: data.contractor?.name ?? "—",
              },
              { label: t("contract.field.nif"), value: data.contractor?.tax_id ?? "—" },
              { label: t("contract.field.rawName"), value: data.raw_contractor_name },
            ]}
          />
        </SectionCard>

        <SectionCard title={t("contract.section.classification")}>
          <DefinitionList
            items={[
              {
                label: t("contract.field.cpv"),
                value: data.cpv_code
                  ? `${data.cpv_code}${data.cpv_description ? ` — ${data.cpv_description}` : ""}`
                  : "—",
              },
              {
                label: t("contract.field.nuts"),
                value: data.nuts_code
                  ? `${data.nuts_code}${data.nuts_description ? ` — ${data.nuts_description}` : ""}`
                  : "—",
              },
              { label: t("contract.field.financing"), value: data.financing },
            ]}
          />
        </SectionCard>

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
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="py-1 pr-2 font-medium">
                    #
                  </th>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contract.criteria.name")}
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    {t("contract.criteria.weight")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {criteria.data?.data.map((criterion) => (
                  <tr key={criterion.id} className="border-t border-line">
                    <td className="py-1.5 pr-2 tabular-nums text-muted">{criterion.position}</td>
                    <td className="py-1.5 pr-2">{criterion.name}</td>
                    <td className="py-1.5 text-right tabular-nums">
                      {criterion.weight ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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

      <div className="mt-4">
        <ContractTasks contractId={id} />
      </div>

      {(documents.data?.data.length ?? 0) > 0 && (
        <div className="mt-4">
          <SectionCard
            title={`${t("contract.section.documents")} (${documents.data?.data.length ?? 0})`}
          >
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contract.documents.title")}
                  </th>
                  <th scope="col" className="py-1 pr-2 font-medium">
                    {t("contract.documents.phase")}
                  </th>
                  <th scope="col" className="py-1 text-right font-medium">
                    {t("contract.documents.size")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {documents.data?.data.map((document) => (
                  <tr key={document.id} className="border-t border-line">
                    <td className="py-1.5 pr-2">
                      {document.download_url ? (
                        <a
                          href={document.download_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent underline-offset-2 hover:underline"
                          aria-label={`${document.title ?? ""} — ${t("contract.documents.open")}`}
                        >
                          {document.title ?? "—"} ↗
                        </a>
                      ) : (
                        (document.title ?? "—")
                      )}
                    </td>
                    <td className="py-1.5 pr-2 text-muted">{phaseLabel(document.phase)}</td>
                    <td className="py-1.5 text-right tabular-nums text-muted">
                      {formatBytes(document.size)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </SectionCard>
        </div>
      )}

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
    </div>
  );
}
