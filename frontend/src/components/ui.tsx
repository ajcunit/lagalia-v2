/** Peces petites del sistema de disseny (10-ui.md §2): tot amb tokens. */

import type { ReactNode } from "react";

export function Badge(props: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "accent";
}) {
  const tone = props.tone ?? "neutral";
  const tones: Record<string, string> = {
    neutral: "bg-surface-sunken text-muted",
    success: "bg-accent-soft text-success",
    warning: "bg-accent-soft text-warning",
    danger: "bg-accent-soft text-danger",
    accent: "bg-accent-soft text-accent",
  };
  return (
    <span
      className={`inline-block rounded-md px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {props.children}
    </span>
  );
}

export function EmptyState(props: { icon?: string; title: string; detail?: string }) {
  return (
    <div className="py-16 text-center">
      <p aria-hidden="true" className="text-3xl">
        {props.icon ?? "🗂️"}
      </p>
      <p className="mt-3 font-medium text-ink">{props.title}</p>
      {props.detail && <p className="mt-1 text-sm text-muted">{props.detail}</p>}
    </div>
  );
}

export function Skeleton(props: { rows?: number }) {
  return (
    <div role="status" aria-label="Carregant" className="animate-pulse space-y-2 py-4">
      {Array.from({ length: props.rows ?? 8 }).map((_, index) => (
        <div key={index} className="h-9 rounded-md bg-surface-sunken" />
      ))}
    </div>
  );
}

export function SectionCard(props: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-surface-raised p-5 shadow-card">
      <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
        {props.title}
      </h2>
      <div className="mt-3">{props.children}</div>
    </section>
  );
}

export function DefinitionList(props: {
  items: Array<{ label: string; value: ReactNode }>;
}) {
  return (
    <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
      {props.items.map((item) => (
        <div key={item.label} className="flex flex-col">
          <dt className="text-xs text-muted">{item.label}</dt>
          <dd className="text-sm text-ink">{item.value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
