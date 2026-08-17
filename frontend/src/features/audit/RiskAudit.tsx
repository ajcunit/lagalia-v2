import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { Button, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { ShieldAlert } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";
import { streamNdjson } from "../../lib/stream";
import { Markdown } from "../../components/Markdown";

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

function AiReport() {
  const [customPrompt, setCustomPrompt] = useState("");
  const [copied, setCopied] = useState(false);
  const [report, setReport] = useState("");
  const [thinkingChars, setThinkingChars] = useState(0);
  const [sendResult, setSendResult] = useState<string | null>(null);
  const sendNow = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/ai/audit/report/send-now", {});
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: (result) =>
      setSendResult(
        result.emailed > 0
          ? t("riskAudit.sentOk", { count: String(result.emailed) })
          : t("riskAudit.sentNone", { detail: result.detail ?? "" }),
      ),
    onError: () => setSendResult(t("riskAudit.aiError")),
  });
  const generate = useMutation({
    mutationFn: async () => {
      setReport("");
      setThinkingChars(0);
      let failed: string | null = null;
      await streamNdjson(
        "/ai/audit/report/stream",
        { custom_prompt: customPrompt.trim() || null },
        (event) => {
          if (event.type === "delta") setReport((prev) => prev + String(event.text ?? ""));
          if (event.type === "thinking")
            setThinkingChars((prev) => prev + String(event.text ?? "").length);
          if (event.type === "error") failed = String(event.detail ?? "error");
        },
      );
      if (failed !== null) throw new Error(failed);
    },
  });

  return (
    <div className="mt-6 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card">
      <h2 className="text-lg font-semibold text-ink">{t("riskAudit.aiTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{t("riskAudit.aiIntro")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <textarea
          value={customPrompt}
          onChange={(e) => setCustomPrompt(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder={t("riskAudit.aiPlaceholder")}
          className="min-w-72 flex-1 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
        />
        <Button tone="accent" disabled={generate.isPending} onClick={() => generate.mutate()}>
          {generate.isPending ? t("riskAudit.aiGenerating") : t("riskAudit.aiGenerate")}
        </Button>
        <Button disabled={sendNow.isPending} onClick={() => sendNow.mutate()}>
          {sendNow.isPending ? t("riskAudit.sending") : t("riskAudit.sendNow")}
        </Button>
      </div>
      {sendResult && (
        <p role="status" className="mt-2 rounded-md bg-accent-soft p-2 text-sm text-ink">
          {sendResult}
        </p>
      )}
      {generate.isPending && report === "" && (
        <p role="status" className="mt-2 animate-pulse text-sm text-muted">
          {thinkingChars > 0
            ? t("riskAudit.aiThinkingLive", { chars: String(thinkingChars) })
            : t("riskAudit.aiGenerating")}
        </p>
      )}
      {generate.isError && (
        <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
          {t("riskAudit.aiError")}
        </p>
      )}
      {report && (
        <div className="mt-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <button
              type="button"
              className="underline"
              onClick={() => {
                void navigator.clipboard.writeText(report);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
            >
              {copied ? t("cpv.copied") : t("cpv.copy")}
            </button>
          </div>
          <div className="mt-1 max-h-[32rem] overflow-auto rounded-md bg-surface p-4">
            <Markdown>{report}</Markdown>
            {generate.isPending && <span className="animate-pulse text-muted">▍</span>}
          </div>
          <p className="mt-1 text-xs text-muted">{t("riskAudit.aiDisclaimer")}</p>
        </div>
      )}
    </div>
  );
}

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
      <PageHeader icon={ShieldAlert} title={t("riskAudit.title")} subtitle={t("riskAudit.intro")} />
      <AiReport />
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
