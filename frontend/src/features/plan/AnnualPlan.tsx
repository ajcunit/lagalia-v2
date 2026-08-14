import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Badge, Button, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";

type Entry = components["schemas"]["PlanEntry"];
type Body = components["schemas"]["PlanEntryBody"];

const QUARTERS = [1, 2, 3, 4] as const;

function EntryForm(props: { year: number; entry?: Entry; onDone: () => void }) {
  const queryClient = useQueryClient();
  const e = props.entry;
  const [subject, setSubject] = useState(e?.subject ?? "");
  const [quarter, setQuarter] = useState(e?.quarter ?? 1);
  const [contractType, setContractType] = useState(e?.contract_type ?? "");
  const [amount, setAmount] = useState(e?.estimated_amount ? String(e.estimated_amount) : "");
  const [subsidized, setSubsidized] = useState(e?.subsidized ?? false);
  const [notes, setNotes] = useState(e?.notes ?? "");

  const save = useMutation({
    mutationFn: async () => {
      const body: Body = {
        fiscal_year: props.year,
        quarter,
        subject,
        contract_type: contractType || null,
        estimated_amount: amount ? Number(amount) : null,
        subsidized,
        notes: notes || null,
      };
      if (e) {
        const { error } = await api.PATCH("/plan/{id}", {
          params: { path: { id: e.id } },
          body,
        });
        if (error !== undefined) throw error;
      } else {
        const { error } = await api.POST("/plan", { body });
        if (error !== undefined) throw error;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["plan"] });
      props.onDone();
    },
  });

  return (
    <form
      className="flex flex-wrap items-end gap-2 rounded-md border border-line bg-surface p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (subject.trim()) save.mutate();
      }}
    >
      <label className="min-w-64 flex-1 text-sm text-ink">
        {t("plan.subject")}
        <input value={subject} onChange={(ev) => setSubject(ev.target.value)} required maxLength={1000}
          className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm" />
      </label>
      <label className="text-sm text-ink">
        {t("plan.quarter")}
        <select value={quarter} onChange={(ev) => setQuarter(Number(ev.target.value))}
          className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm">
          {QUARTERS.map((q) => <option key={q} value={q}>T{q}</option>)}
        </select>
      </label>
      <label className="text-sm text-ink">
        {t("plan.type")}
        <input value={contractType} onChange={(ev) => setContractType(ev.target.value)} maxLength={100}
          className="mt-1 block w-36 rounded-md border border-line bg-surface px-2 py-1.5 text-sm" />
      </label>
      <label className="text-sm text-ink">
        {t("plan.amount")}
        <input type="number" min="0" value={amount} onChange={(ev) => setAmount(ev.target.value)}
          className="mt-1 block w-32 rounded-md border border-line bg-surface px-2 py-1.5 text-sm" />
      </label>
      <label className="flex items-center gap-1 text-sm text-ink">
        <input type="checkbox" checked={subsidized} onChange={(ev) => setSubsidized(ev.target.checked)} />
        {t("plan.subsidized")}
      </label>
      <label className="min-w-48 flex-1 text-sm text-ink">
        {t("plan.notes")}
        <input value={notes} onChange={(ev) => setNotes(ev.target.value)} maxLength={2000}
          className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm" />
      </label>
      <Button tone="accent" disabled={save.isPending} onClick={() => subject.trim() && save.mutate()}>
        {e ? t("admin.save") : t("plan.add")}
      </Button>
      {e && <Button onClick={props.onDone}>{t("favorites.cancel")}</Button>}
    </form>
  );
}

function LegalReview(props: { year: number }) {
  const review = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/compliance/check-plan", {
        body: { fiscal_year: props.year },
      });
      if (error !== undefined) throw error;
      return data.data as {
        entry_id: number;
        subject: string;
        quarter: number;
        status: string;
        findings: { article?: string; detail?: string; status?: string }[];
      }[];
    },
  });
  const tone = (status: string) =>
    status === "conforme" ? "accent" : status === "avis" ? "neutral" : "danger";

  return (
    <div className="mt-6 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-ink">{t("plan.legalTitle")}</h2>
          <p className="mt-1 text-sm text-muted">{t("plan.legalIntro")}</p>
        </div>
        <Button tone="accent" disabled={review.isPending} onClick={() => review.mutate()}>
          {review.isPending ? t("plan.legalRunning") : t("plan.legalRun")}
        </Button>
      </div>
      {review.isError && (
        <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
          {t("admin.loadError")}
        </p>
      )}
      {review.data && (
        <div className="mt-3">
          {review.data.length === 0 ? (
            <p className="text-sm text-muted">{t("plan.legalEmpty")}</p>
          ) : (
            review.data.map((row) => (
              <div key={row.entry_id} className="flex flex-wrap items-start gap-2 border-t border-line py-1.5 first:border-t-0">
                <Badge tone={tone(row.status)}>{t(`plan.legal.${row.status}` as never)}</Badge>
                <span className="text-sm text-muted">T{row.quarter}</span>
                <span className="min-w-0 flex-1 text-sm text-ink">{row.subject}</span>
                <span className="w-full pl-2 text-xs text-muted">
                  {row.findings
                    .filter((f) => f.status !== "conforme")
                    .map((f) => `${f.detail} (${f.article})`)
                    .join(" · ") || row.findings.map((f) => f.detail).join(" · ")}
                </span>
              </div>
            ))
          )}
          <p className="mt-2 text-xs text-muted">{t("plan.legalDisclaimer")}</p>
        </div>
      )}
    </div>
  );
}

export function AnnualPlan() {
  const { permissions } = useAuth();
  const canWrite = permissions?.actions.includes("plan:write") ?? false;
  const canApprove = permissions?.actions.includes("plan:approve") ?? false;
  const queryClient = useQueryClient();
  const now = new Date().getFullYear();
  const [year, setYear] = useState(now);
  const [editing, setEditing] = useState<Entry | null>(null);

  const entries = useQuery({
    queryKey: ["plan", year],
    queryFn: async () => {
      const { data, error } = await api.GET("/plan", { params: { query: { fiscal_year: year } } });
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const expiring = useQuery({
    queryKey: ["plan-expiring", year],
    queryFn: async () => {
      const { data, error } = await api.GET("/plan/expiring", {
        params: { query: { fiscal_year: year } },
      });
      if (error !== undefined) throw error;
      return data.data as Record<string, unknown>[];
    },
  });

  const act = useMutation({
    mutationFn: async (input: { id: number; action: "approve" | "delete" }) => {
      if (input.action === "approve") {
        const { error } = await api.POST("/plan/{id}/actions/approve", {
          params: { path: { id: input.id } },
        });
        if (error !== undefined) throw error;
      } else {
        const { error } = await api.DELETE("/plan/{id}", { params: { path: { id: input.id } } });
        if (error !== undefined) throw error;
      }
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["plan"] }),
  });

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{t("plan.title")}</h1>
        <select value={year} onChange={(ev) => setYear(Number(ev.target.value))}
          aria-label={t("plan.year")}
          className="ml-auto rounded-md border border-line bg-surface px-2 py-1.5 text-sm">
          {[now - 1, now, now + 1, now + 2, now + 3].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
      </div>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("plan.intro")}</p>

      {canWrite && !editing && (
        <div className="mt-4"><EntryForm year={year} onDone={() => undefined} /></div>
      )}
      {editing && (
        <div className="mt-4"><EntryForm year={year} entry={editing} onDone={() => setEditing(null)} /></div>
      )}

      <div className="mt-4 space-y-4">
        {entries.isPending ? (
          <Skeleton rows={6} />
        ) : entries.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (
          QUARTERS.map((q) => {
            const rows = (entries.data ?? []).filter((entry) => entry.quarter === q);
            return (
              <SectionCard key={q} title={`${t("plan.quarterTitle")} ${q} (${rows.length})`}>
                {rows.length === 0 ? (
                  <p className="text-sm text-muted">{t("plan.quarterEmpty")}</p>
                ) : (
                  rows.map((entry) => (
                    <div key={entry.id} className="flex flex-wrap items-center gap-2 border-t border-line py-1.5 first:border-t-0">
                      <span className="min-w-0 flex-1 text-sm text-ink">
                        {entry.subject}
                        {entry.contract_type && <span className="text-muted"> · {entry.contract_type}</span>}
                        {entry.contract_file_code && (
                          <Link to={`/contracts/${entry.contract_id}`} className="ml-1 font-mono text-xs text-accent underline">
                            {entry.contract_file_code}
                          </Link>
                        )}
                      </span>
                      {entry.subsidized && <Badge tone="neutral">{t("plan.subsidized")}</Badge>}
                      {entry.estimated_amount != null && (
                        <span className="text-sm text-ink">{formatCurrency(String(entry.estimated_amount))}</span>
                      )}
                      <Badge tone={entry.status === "approved" ? "accent" : "danger"}>
                        {t(`plan.status.${entry.status}`)}
                      </Badge>
                      {canApprove && entry.status === "pending" && (
                        <Button disabled={act.isPending} onClick={() => act.mutate({ id: entry.id, action: "approve" })}>
                          {t("plan.approve")}
                        </Button>
                      )}
                      {canWrite && (
                        <>
                          <button type="button" className="text-xs text-muted underline" onClick={() => setEditing(entry)}>
                            {t("favorites.edit")}
                          </button>
                          <button type="button" className="text-xs text-danger underline"
                            onClick={() => {
                              if (window.confirm(t("plan.confirmDelete"))) act.mutate({ id: entry.id, action: "delete" });
                            }}>
                            ✕
                          </button>
                        </>
                      )}
                    </div>
                  ))
                )}
              </SectionCard>
            );
          })
        )}
      </div>

      <LegalReview year={year} />

      <h2 className="mt-6 text-lg font-semibold text-ink">{t("plan.expiring")}</h2>
      <p className="mt-1 text-sm text-muted">{t("plan.expiringIntro")}</p>
      <div className="mt-2 rounded-lg border border-line bg-surface-raised p-3 shadow-card">
        {expiring.isPending ? (
          <Skeleton rows={4} />
        ) : expiring.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (expiring.data ?? []).length === 0 ? (
          <p className="text-sm text-muted">{t("plan.expiringEmpty")}</p>
        ) : (
          (expiring.data ?? []).map((row, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2 border-t border-line py-1.5 first:border-t-0 text-sm">
              <Badge tone="neutral">T{String(row.quarter)}</Badge>
              <Link to={`/contracts/${String(row.contract_id)}`} className="font-mono text-xs text-accent underline">
                {String(row.file_code)}
              </Link>
              <span className="min-w-0 flex-1 text-ink">{String(row.subject ?? "")}</span>
              <span className="text-muted">{formatDate(String(row.end_date))}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
