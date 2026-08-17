import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { Globe } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatBytes, formatCurrency, formatDate } from "../../lib/format";
import { useFolders } from "../favorites/useFolders";

type Card = components["schemas"]["PublicContractCard"];

/** Ordre canònic de fases del portal (02 §2.10). */
const PHASE_ORDER = [
  "futura",
  "agregada",
  "cpm",
  "previ",
  "licitacio",
  "avaluacio",
  "adjudicacio",
  "formalitzacio",
  "anulacio",
] as const;

type PhaseKey = (typeof PHASE_ORDER)[number];

function phasesOf(card: Card): { phase: PhaseKey; url: string }[] {
  const urls = card.phase_urls ?? {};
  return PHASE_ORDER.flatMap((phase) => {
    const url = urls[phase];
    return typeof url === "string" && url ? [{ phase, url }] : [];
  });
}

function AddToProject(props: { title: string; downloadUrl: string; fileCode: string }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const projects = useQuery({
    queryKey: ["doc-projects"],
    enabled: open,
    queryFn: async () => {
      const { data, error } = await api.GET("/doc-projects");
      if (error !== undefined) throw error;
      return data.data as { id: number; name: string }[];
    },
  });
  const add = useMutation({
    mutationFn: async (projectId: number) => {
      const { error } = await api.POST("/doc-projects/{id}/external-references", {
        params: { path: { id: projectId } },
        body: { title: props.title, source_url: props.downloadUrl, file_code: props.fileCode },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => {
      setMessage(t("search.addedToProject"));
      setOpen(false);
    },
    onError: () => {
      setMessage(t("favorites.saveError"));
      setOpen(false);
    },
  });

  return (
    <span className="relative">
      <button
        type="button"
        aria-expanded={open}
        className="text-xs text-muted underline hover:text-ink"
        onClick={() => setOpen(!open)}
      >
        {t("search.addToProject")}
      </button>
      {message && <span className="ml-1 text-xs text-muted">{message}</span>}
      {open && (
        <span className="absolute right-0 top-5 z-10 block w-56 rounded-md border border-line bg-surface-raised p-2 shadow-card">
          {(projects.data ?? []).length === 0 ? (
            <span className="block text-xs text-muted">{t("search.noProjectsHint")}</span>
          ) : (
            (projects.data ?? []).map((project) => (
              <button
                key={project.id}
                type="button"
                disabled={add.isPending}
                className="block w-full rounded px-2 py-1 text-left text-sm text-ink hover:bg-accent-soft"
                onClick={() => add.mutate(project.id)}
              >
                {project.name}
              </button>
            ))
          )}
        </span>
      )}
    </span>
  );
}

function PhasePanel(props: { url: string; fileCode: string }) {
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

  if (phase.isPending) return <Skeleton rows={3} />;
  if (phase.isError) return <p className="text-sm text-muted">{t("search.phaseError")}</p>;

  const { documents, committee, criteria } = phase.data;
  if (documents.length === 0 && committee.length === 0 && criteria.length === 0) {
    return <p className="text-sm text-muted">{t("search.phaseEmpty")}</p>;
  }
  return (
    <div className="space-y-3">
      {documents.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-ink">{t("search.documents")}</h4>
          <ul className="mt-1 space-y-1">
            {documents.map((doc) => (
              <li key={doc.source_doc_id} className="flex flex-wrap items-center gap-2 text-sm">
                <a
                  href={doc.download_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent underline"
                >
                  {doc.title}
                </a>
                <span className="text-xs text-muted">
                  {doc.doc_type}
                  {doc.size ? ` · ${formatBytes(doc.size)}` : ""}
                </span>
                <AddToProject
                  title={doc.title}
                  downloadUrl={doc.download_url}
                  fileCode={props.fileCode}
                />
              </li>
            ))}
          </ul>
        </div>
      )}
      {criteria.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-ink">{t("search.criteria")}</h4>
          <ul className="mt-1 space-y-0.5 text-sm">
            {criteria.map((criterion, index) => (
              <li key={index}>
                {String(criterion.name ?? "—")}
                {criterion.weight !== null && criterion.weight !== undefined && (
                  <span className="text-muted"> · {String(criterion.weight)}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {committee.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-ink">{t("search.committee")}</h4>
          <ul className="mt-1 space-y-0.5 text-sm">
            {committee.map((member, index) => {
              const name = [member.first_name, member.last_name]
                .filter((part): part is string => typeof part === "string" && part.length > 0)
                .join(" ");
              const role = typeof member.role === "string" ? member.role : null;
              return (
                <li key={index}>
                  {name || "—"}
                  {role && <span className="text-muted"> · {role}</span>}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function SaveToFolder(props: { fileCode: string }) {
  const queryClient = useQueryClient();
  const folders = useFolders();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const add = useMutation({
    mutationFn: async (folderId: number) => {
      const { error, response } = await api.POST("/folders/{id}/favorites", {
        params: { path: { id: folderId } },
        body: { file_code: props.fileCode },
      });
      if (error !== undefined) throw Object.assign(new Error(), { status: response.status });
    },
    onSuccess: () => {
      setMessage(t("favorites.saved"));
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["folders"] });
    },
    onError: (error: Error & { status?: number }) => {
      setMessage(error.status === 409 ? t("favorites.alreadySaved") : t("favorites.saveError"));
      setOpen(false);
    },
  });

  const list = folders.data?.data ?? [];
  return (
    <span className="relative">
      <button
        type="button"
        aria-expanded={open}
        className="text-xs text-muted underline hover:text-ink"
        onClick={() => setOpen(!open)}
      >
        ⭐ {t("favorites.save")}
      </button>
      {message && <span className="ml-1 text-xs text-muted">{message}</span>}
      {open && (
        <span className="absolute right-0 top-6 z-10 block w-56 rounded-md border border-line bg-surface-raised p-2 shadow-card">
          {list.length === 0 ? (
            <span className="block text-xs text-muted">{t("favorites.noFoldersHint")}</span>
          ) : (
            list.map((folder) => (
              <button
                key={folder.id}
                type="button"
                disabled={add.isPending}
                className="block w-full rounded px-2 py-1 text-left text-sm text-ink hover:bg-accent-soft"
                onClick={() => add.mutate(folder.id)}
              >
                {folder.name}
              </button>
            ))
          )}
        </span>
      )}
    </span>
  );
}

function ResultCard(props: { card: Card }) {
  const c = props.card;
  const [openPhase, setOpenPhase] = useState<string | null>(null);
  const phases = phasesOf(c);
  const profileUrl = c.links?.enllac_perfil_contractant ?? c.links?.enllac_publicacio;

  return (
    <article className="rounded-lg border border-line bg-surface-raised p-4 shadow-card">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-ink">{c.subject ?? c.file_code}</h3>
          <p className="mt-0.5 text-sm text-muted">
            {c.awarding_body}
            {c.awarding_department ? ` · ${c.awarding_department}` : ""}
          </p>
        </div>
        <div className="text-right text-sm">
          <p className="font-mono text-xs text-muted">
            {c.file_code}
            {c.lot ? ` · lot ${c.lot}` : ""}
          </p>
          <p className="text-muted">{c.published_at ? formatDate(c.published_at) : ""}</p>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {c.contract_type && <Badge tone="neutral">{c.contract_type}</Badge>}
        {c.procedure && <Badge tone="neutral">{c.procedure}</Badge>}
        {c.status && <Badge tone="accent">{c.status}</Badge>}
        <span className="ml-auto text-ink">
          {c.budget_vat !== null && c.budget_vat !== undefined && (
            <>
              {t("search.budget")}: <strong>{formatCurrency(c.budget_vat)}</strong>
            </>
          )}
          {c.award_amount !== null && c.award_amount !== undefined && (
            <>
              {" · "}
              {t("search.award")}: <strong>{formatCurrency(c.award_amount)}</strong>
            </>
          )}
        </span>
      </div>
      {c.contractor_name && (
        <p className="mt-1 text-sm text-muted">
          {t("search.contractor")}: <span className="text-ink">{c.contractor_name}</span>
          {c.contractor_nif ? ` (${c.contractor_nif})` : ""}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line pt-2">
          {phases.map(({ phase }) => (
            <button
              key={phase}
              type="button"
              aria-expanded={openPhase === phase}
              onClick={() => setOpenPhase(openPhase === phase ? null : phase)}
              className={`rounded-full border px-2.5 py-0.5 text-xs ${
                openPhase === phase
                  ? "border-accent bg-accent-soft text-ink"
                  : "border-line text-muted hover:text-ink"
              }`}
            >
              {t(`search.phase.${phase}` as const)}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-3">
            <SaveToFolder fileCode={c.file_code} />
            {profileUrl && (
              <a
                href={profileUrl}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-accent underline"
              >
                {t("search.openInPortal")}
              </a>
            )}
          </span>
        </div>
      {openPhase !== null &&
        (() => {
          const active = phases.find((entry) => entry.phase === openPhase);
          return active ? (
            <div className="mt-2 rounded-md bg-surface p-3">
              <PhasePanel url={active.url} fileCode={c.file_code} />
            </div>
          ) : null;
        })()}
    </article>
  );
}

export function SuperSearch() {
  const [params, setParams] = useSearchParams();
  const applied = {
    q: params.get("q") ?? "",
    organisme: params.get("organisme") ?? "",
    amount_min: params.get("amount_min") ?? "",
    amount_max: params.get("amount_max") ?? "",
    from: params.get("from") ?? "",
    to: params.get("to") ?? "",
    page: Math.max(1, Number(params.get("page") ?? "1") || 1),
  };
  const [form, setForm] = useState({ ...applied });
  const hasQuery = [applied.q, applied.organisme, applied.amount_min, applied.amount_max, applied.from, applied.to].some(Boolean);

  const results = useQuery({
    queryKey: ["public-search", applied],
    enabled: hasQuery,
    staleTime: 60 * 1000,
    queryFn: async () => {
      const { data, error } = await api.GET("/public-registry/search", {
        params: {
          query: {
            ...(applied.q ? { q: applied.q } : {}),
            ...(applied.organisme ? { "filter[organisme]": applied.organisme } : {}),
            ...(applied.amount_min ? { "filter[amount_min]": Number(applied.amount_min) } : {}),
            ...(applied.amount_max ? { "filter[amount_max]": Number(applied.amount_max) } : {}),
            ...(applied.from ? { "filter[from]": new Date(applied.from).toISOString() } : {}),
            ...(applied.to ? { "filter[to]": new Date(applied.to).toISOString() } : {}),
            page: applied.page,
            page_size: 20,
          },
        },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  function apply(page = 1) {
    const next = new URLSearchParams();
    if (form.q) next.set("q", form.q);
    if (form.organisme) next.set("organisme", form.organisme);
    if (form.amount_min) next.set("amount_min", form.amount_min);
    if (form.amount_max) next.set("amount_max", form.amount_max);
    if (form.from) next.set("from", form.from);
    if (form.to) next.set("to", form.to);
    if (page > 1) next.set("page", String(page));
    setParams(next);
  }

  function goToPage(page: number) {
    const next = new URLSearchParams(params);
    if (page > 1) next.set("page", String(page));
    else next.delete("page");
    setParams(next);
  }

  return (
    <div>
      <PageHeader icon={Globe} title={t("search.title")} subtitle={t("search.intro")} />

      <form
        className="mt-4 space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          apply();
        }}
      >
        <div className="flex flex-wrap gap-2">
          <label className="min-w-64 flex-1">
            <span className="sr-only">{t("search.queryLabel")}</span>
            <input
              type="search"
              value={form.q}
              onChange={(e) => setForm({ ...form, q: e.target.value })}
              placeholder={t("search.queryPlaceholder")}
              className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-base shadow-sm"
            />
          </label>
          <Button tone="accent" onClick={() => apply()}>
            {t("search.submit")}
          </Button>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm text-ink">
            {t("search.filterOrganisme")}
            <input
              value={form.organisme}
              onChange={(e) => setForm({ ...form, organisme: e.target.value })}
              placeholder={t("search.organismePlaceholder")}
              className="mt-1 block w-56 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-sm text-ink">
            {t("search.filterAmountMin")}
            <input
              type="number"
              min="0"
              value={form.amount_min}
              onChange={(e) => setForm({ ...form, amount_min: e.target.value })}
              className="mt-1 block w-32 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-sm text-ink">
            {t("search.filterAmountMax")}
            <input
              type="number"
              min="0"
              value={form.amount_max}
              onChange={(e) => setForm({ ...form, amount_max: e.target.value })}
              className="mt-1 block w-32 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-sm text-ink">
            {t("search.filterFrom")}
            <input
              type="date"
              value={form.from}
              onChange={(e) => setForm({ ...form, from: e.target.value })}
              className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            />
          </label>
          <label className="text-sm text-ink">
            {t("search.filterTo")}
            <input
              type="date"
              value={form.to}
              onChange={(e) => setForm({ ...form, to: e.target.value })}
              className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            />
          </label>
        </div>
      </form>

      <div className="mt-5">
        {!hasQuery ? (
          <EmptyState icon="🔭" title={t("search.startTitle")} detail={t("search.startDetail")} />
        ) : results.isPending ? (
          <div className="space-y-3">
            <Skeleton rows={4} />
            <Skeleton rows={4} />
          </div>
        ) : results.isError ? (
          <EmptyState icon="⚠️" title={t("search.error")} />
        ) : results.data.data.length === 0 ? (
          <EmptyState icon="🔍" title={t("search.noResults")} detail={t("search.noResultsDetail")} />
        ) : (
          <>
            <div className="space-y-3">
              {results.data.data.map((card) => (
                <ResultCard key={`${card.file_code}|${card.lot}|${card.status}`} card={card} />
              ))}
            </div>
            <nav className="mt-4 flex items-center gap-2" aria-label={t("search.pagination")}>
              <Button disabled={applied.page <= 1} onClick={() => goToPage(applied.page - 1)}>
                {t("contracts.prev")}
              </Button>
              <span className="text-sm text-muted">
                {t("search.pageLabel", { page: String(applied.page) })}
              </span>
              <Button
                disabled={!results.data.meta.has_more}
                onClick={() => goToPage(applied.page + 1)}
              >
                {t("contracts.next")}
              </Button>
            </nav>
          </>
        )}
      </div>
    </div>
  );
}
