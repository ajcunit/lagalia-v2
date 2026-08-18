import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { formatDate } from "../lib/format";

/** Peces visuals compartides per les fitxes de contracte (municipal i
 * externa): cronograma del procés, barres de criteris i xips de CPV. */

export interface TimelineEvent {
  label: string;
  date: string | null | undefined;
}

function eventState(date: string | null | undefined): "done" | "upcoming" | "pending" {
  if (!date) return "pending";
  return new Date(date).getTime() <= Date.now() ? "done" : "upcoming";
}

export function Timeline(props: { events: TimelineEvent[] }) {
  const events = props.events;
  return (
    <ol className="space-y-0">
      {events.map((event, index) => {
        const state = eventState(event.date);
        return (
          <li key={index} className="relative flex gap-3 pb-5 last:pb-0">
            {index < events.length - 1 && (
              <span
                aria-hidden
                className="absolute left-[7px] top-5 h-full w-px bg-line"
              />
            )}
            <span
              aria-hidden
              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 text-[9px] ${
                state === "done"
                  ? "border-ink bg-ink text-surface"
                  : state === "upcoming"
                    ? "border-ink bg-surface"
                    : "border-line bg-surface"
              }`}
            >
              {state === "done" ? "✓" : ""}
            </span>
            <span className="min-w-0">
              <span
                className={`block text-sm ${state === "pending" ? "text-muted" : "font-medium text-ink"}`}
              >
                {event.label}
              </span>
              <span className="block text-xs text-muted">
                {event.date ? formatDate(event.date) : "—"}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export interface CriterionBar {
  name: string;
  weight: number | string | null | undefined;
  detail?: string | null;
}

export function CriteriaBars(props: { criteria: CriterionBar[]; unit?: string }) {
  const weights = props.criteria.map((c) => Number(c.weight) || 0);
  const max = Math.max(...weights, 1);
  return (
    <ul className="space-y-3">
      {props.criteria.map((criterion, index) => {
        const weight = Number(criterion.weight) || 0;
        return (
          <li key={index}>
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-ink">
                {criterion.name}
              </span>
              <span className="shrink-0 text-xs tabular-nums text-muted">
                {criterion.weight === null || criterion.weight === undefined
                  ? "—"
                  : `${criterion.weight} ${props.unit ?? "pts"}`}
              </span>
            </div>
            {criterion.detail && (
              <p className="mt-0.5 truncate text-xs text-muted">{criterion.detail}</p>
            )}
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface">
              <div
                className="h-full rounded-full bg-accent"
                style={{ width: `${Math.max(2, (weight / max) * 100)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function CpvChips(props: { code: string | null | undefined; description?: string | null }) {
  const codes = (props.code ?? "").split("||").map((code) => code.trim()).filter(Boolean);

  // Descripcions del catàleg CPV sincronitzat (GET /cpv cerca per prefix de codi).
  const lookups = useQuery({
    queryKey: ["cpv-descriptions", codes],
    enabled: codes.length > 0,
    staleTime: Infinity,
    queryFn: async () => {
      const entries = await Promise.all(
        codes.map(async (code) => {
          const clean = code.split("-")[0] ?? code;
          const { data, error } = await api.GET("/cpv", {
            params: { query: { query: clean } },
          });
          if (error !== undefined) return [code, null] as const;
          const hit =
            data.data.find((row) => row.code.startsWith(clean)) ?? data.data[0];
          return [code, hit?.description ?? null] as const;
        }),
      );
      return Object.fromEntries(entries) as Record<string, string | null>;
    },
  });

  if (codes.length === 0) return <p className="text-sm text-muted">—</p>;
  return (
    <ul className="space-y-2">
      {codes.map((code, index) => {
        const description =
          lookups.data?.[code] ?? (index === 0 ? (props.description ?? null) : null);
        return (
          <li key={code} className="rounded-md bg-surface p-2">
            <span className="font-mono text-xs font-semibold text-accent">{code}</span>
            {description ? (
              <span className="mt-0.5 block text-xs text-muted">{description}</span>
            ) : lookups.isPending && codes.length > 0 ? (
              <span className="mt-0.5 block animate-pulse text-xs text-muted">…</span>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

import type { LucideIcon } from "lucide-react";

export interface SheetTab {
  key: string;
  label: string;
  count?: number | null;
  icon?: LucideIcon;
}

/** Barra de pestanyes de la fitxa (estil «Resum · Documents (n) · …»). */
export function SheetTabs(props: {
  tabs: SheetTab[];
  active: string;
  onSelect: (key: string) => void;
}) {
  return (
    <div role="tablist" className="flex flex-wrap gap-1 border-b border-line">
      {props.tabs.map((tab) => {
        const active = props.active === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => props.onSelect(tab.key)}
            className={`-mb-px inline-flex items-center gap-1.5 rounded-t-md border-b-2 px-3 py-2 text-sm ${
              active
                ? "border-accent font-semibold text-ink"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {tab.icon !== undefined && (
              <tab.icon aria-hidden className={`h-4 w-4 ${active ? "text-accent" : ""}`} />
            )}
            {tab.label}
            {tab.count !== undefined && tab.count !== null && (
              <span className="ml-1 text-xs text-muted">({tab.count})</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Parell etiqueta/valor de la graella «Informació rellevant». */
export function InfoPair(props: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line/60 py-1.5 last:border-0">
      <span className="text-sm text-muted">{props.label}</span>
      <span className="text-right text-sm font-medium text-ink">{props.value ?? "—"}</span>
    </div>
  );
}
