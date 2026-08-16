import { ArrowLeft, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { t } from "../i18n";

/** Capçalera de pàgina compartida (B-015): icona, títol, subtítol i accions. */
export function PageHeader(props: {
  icon?: LucideIcon;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  /** Mostra el botó de tornar enrere (pantalles de detall). */
  back?: boolean;
  /** Destí concret; per defecte, l'historial del navegador. */
  backTo?: string;
}) {
  const Icon = props.icon;
  const navigate = useNavigate();
  return (
    <header className="mb-6 flex flex-wrap items-start gap-4">
      {(props.back || props.backTo) && (
        <button
          type="button"
          onClick={() => (props.backTo ? navigate(props.backTo) : navigate(-1))}
          aria-label={t("common.back")}
          className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-line bg-surface-raised text-muted shadow-card hover:bg-surface-sunken hover:text-ink"
        >
          <ArrowLeft aria-hidden className="h-5 w-5" strokeWidth={1.8} />
        </button>
      )}
      {Icon && (
        <span
          aria-hidden
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent"
        >
          <Icon className="h-6 w-6" strokeWidth={1.8} />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink">{props.title}</h1>
        {props.subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{props.subtitle}</p>}
      </div>
      {props.actions && <div className="flex flex-wrap items-center gap-2">{props.actions}</div>}
    </header>
  );
}
