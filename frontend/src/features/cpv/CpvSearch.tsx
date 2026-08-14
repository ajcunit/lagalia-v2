import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { Badge, EmptyState, Skeleton } from "../../components/ui";
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
      <h1 className="text-2xl font-bold tracking-tight text-ink">{t("cpv.title")}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("cpv.intro")}</p>
      <input
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("cpv.placeholder")}
        aria-label={t("cpv.title")}
        className="mt-4 w-full max-w-xl rounded-lg border border-line bg-surface px-3 py-2.5 text-base shadow-sm"
      />
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
