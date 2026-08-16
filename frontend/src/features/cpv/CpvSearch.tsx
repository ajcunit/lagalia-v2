import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { Search } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";

type CpvRow = {
  code: string;
  description: string;
  level?: string | null;
  parent_code?: string | null;
  has_children: boolean;
};

function useCpv(params: { query?: string; parent?: string }) {
  return useQuery({
    queryKey: ["cpv", params],
    staleTime: 60 * 60 * 1000,
    queryFn: async () => {
      const { data, error } = await api.GET("/cpv", { params: { query: params } });
      if (error !== undefined) throw error;
      return data.data as CpvRow[];
    },
  });
}

function CopyCode(props: { code: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="text-xs text-muted underline hover:text-ink"
      onClick={() => {
        void navigator.clipboard.writeText(props.code);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? t("cpv.copied") : t("cpv.copy")}
    </button>
  );
}

function Row(props: { row: CpvRow; depth: number }) {
  const [open, setOpen] = useState(false);
  const children = useCpv({ parent: props.row.code });
  const r = props.row;
  return (
    <>
      <div
        className="flex items-center gap-2 border-t border-line py-1.5"
        style={{ paddingLeft: `${props.depth * 1.5}rem` }}
      >
        {r.has_children ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen(!open)}
            className="w-5 text-center text-muted"
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-5" />
        )}
        <code className="text-xs text-accent">{r.code}</code>
        <span className="min-w-0 flex-1 text-sm text-ink">{r.description}</span>
        {r.level && <Badge tone="neutral">{t(`cpv.level.${r.level}` as never)}</Badge>}
        <CopyCode code={r.code} />
      </div>
      {open &&
        (children.isPending ? (
          <div style={{ paddingLeft: `${(props.depth + 1) * 1.5}rem` }}>
            <Skeleton rows={1} />
          </div>
        ) : (
          (children.data ?? []).map((childRow) => (
            <Row key={childRow.code} row={childRow} depth={props.depth + 1} />
          ))
        ))}
    </>
  );
}

type Suggestion = { code: string; description: string; score: number; justification: string };

function AiSuggest() {
  const [text, setText] = useState("");
  const [copied, setCopied] = useState<string | null>(null);

  const suggest = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/ai/cpv/suggest", { body: { text } });
      if (error !== undefined) throw error;
      return data;
    },
  });

  function pick(item: Suggestion, all: Suggestion[]) {
    void navigator.clipboard.writeText(item.code);
    setCopied(item.code);
    setTimeout(() => setCopied(null), 2000);
    void api.POST("/ai/cpv/feedback", {
      body: { query_text: text, chosen_code: item.code, suggested: all },
    });
  }

  return (
    <div className="mt-6 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card">
      <h2 className="text-lg font-semibold text-ink">{t("cpv.aiTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{t("cpv.aiIntro")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder={t("cpv.aiPlaceholder")}
          className="min-w-72 flex-1 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
        />
        <Button
          tone="accent"
          disabled={suggest.isPending || text.trim().length < 5}
          onClick={() => suggest.mutate()}
        >
          {suggest.isPending ? t("cpv.aiThinking") : t("cpv.aiSubmit")}
        </Button>
      </div>
      {suggest.isError && (
        <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
          {t("cpv.aiError")}
        </p>
      )}
      {suggest.data && (
        <div className="mt-3 space-y-2">
          {suggest.data.suggestions.length === 0 ? (
            <p className="text-sm text-muted">{t("cpv.aiEmpty")}</p>
          ) : (
            suggest.data.suggestions.map((item) => (
              <div key={item.code} className="flex flex-wrap items-start gap-2 rounded-md bg-surface p-2">
                <code className="text-sm font-semibold text-accent">{item.code}</code>
                <Badge tone="neutral">{Math.round(item.score * 100)}%</Badge>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink">{item.description}</p>
                  <p className="text-xs text-muted">{item.justification}</p>
                </div>
                <Button onClick={() => pick(item, suggest.data.suggestions)}>
                  {copied === item.code ? t("cpv.copied") : t("cpv.aiUse")}
                </Button>
              </div>
            ))
          )}
          {suggest.data.source === "lexical" && (
            <p className="text-xs text-muted">{t("cpv.aiLexicalNote")}</p>
          )}
        </div>
      )}
    </div>
  );
}

export function CpvSearch() {
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(text.trim()), 300);
    return () => clearTimeout(handle);
  }, [text]);

  const searching = debounced.length >= 2;
  const results = useCpv(searching ? { query: debounced } : {});

  return (
    <div>
      <PageHeader icon={Search} title={t("cpv.title")} subtitle={t("cpv.intro")} />
      <input
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("cpv.placeholder")}
        aria-label={t("cpv.title")}
        className="mt-4 w-full max-w-xl rounded-lg border border-line bg-surface px-3 py-2.5 text-base shadow-sm"
      />
      <AiSuggest />
      <div className="mt-4 rounded-lg border border-line bg-surface-raised p-3 shadow-card">
        {results.isPending ? (
          <Skeleton rows={8} />
        ) : results.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (results.data ?? []).length === 0 ? (
          <EmptyState icon="🔍" title={t("cpv.empty")} />
        ) : (
          <div>
            {searching && (results.data ?? []).length === 50 && (
              <p className="pb-1 text-xs text-muted">{t("cpv.truncated")}</p>
            )}
            {(results.data ?? []).map((row) => (
              <Row key={row.code} row={row} depth={0} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
