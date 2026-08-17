import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { Globe } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { PhasePanel } from "../../components/PhaseExplorer";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";
import { phasesFromUrls } from "../../lib/phases";
import { useFolders } from "../favorites/useFolders";

type Card = components["schemas"]["PublicContractCard"];

const CONTRACT_TYPES = [
  "Serveis",
  "Subministraments",
  "Obres",
  "Concessió de serveis",
  "Concessió d'obres",
  "Administratiu especial",
] as const;

const PHASES_FILTER = [
  "Anunci previ",
  "Anunci de licitació",
  "Expedient en avaluació",
  "Adjudicació",
  "Formalització",
  "Execució",
  "Anul·lació",
  "Publicació agregada de contractes",
] as const;

function SaveToFolder(props: { fileCode: string }) {
  const queryClient = useQueryClient();
  const folders = useFolders();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

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
  const createAndSave = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/folders", { body: { name: newName } });
      if (error !== undefined) throw error;
      await add.mutateAsync((data as { id: number }).id);
    },
    onSuccess: () => setNewName(""),
    onError: () => {
      setMessage(t("favorites.saveError"));
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
        <span className="absolute right-0 top-6 z-10 block w-64 rounded-md border border-line bg-surface-raised p-2 shadow-card">
          {list.map((folder) => (
            <button
              key={folder.id}
              type="button"
              disabled={add.isPending}
              className="block w-full rounded px-2 py-1 text-left text-sm text-ink hover:bg-accent-soft"
              onClick={() => add.mutate(folder.id)}
            >
              {folder.name}
            </button>
          ))}
          <span
            className={`flex gap-1 ${list.length > 0 ? "mt-1 border-t border-line pt-1.5" : ""}`}
          >
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={t("favorites.newFolderPlaceholder")}
              aria-label={t("favorites.newFolderPlaceholder")}
              className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs"
            />
            <Button
              tone="accent"
              disabled={createAndSave.isPending || !newName.trim()}
              onClick={() => createAndSave.mutate()}
            >
              {t("search.create")}
            </Button>
          </span>
        </span>
      )}
    </span>
  );
}

function ResultCard(props: { card: Card }) {
  const c = props.card;
  const [openPhase, setOpenPhase] = useState<string | null>(null);
  const phases = phasesFromUrls(c.phase_urls);
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
    type: params.get("type") ?? "",
    phase: params.get("phase") ?? "",
    amount_min: params.get("amount_min") ?? "",
    amount_max: params.get("amount_max") ?? "",
    from: params.get("from") ?? "",
    to: params.get("to") ?? "",
    page: Math.max(1, Number(params.get("page") ?? "1") || 1),
  };
  const [form, setForm] = useState({ ...applied });
  const hasQuery = [
    applied.q, applied.organisme, applied.type, applied.phase,
    applied.amount_min, applied.amount_max, applied.from, applied.to,
  ].some(Boolean);
  const activeFilters = [
    applied.organisme, applied.type, applied.phase,
    applied.amount_min, applied.amount_max, applied.from, applied.to,
  ].filter(Boolean).length;

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
            ...(applied.type ? { "filter[contract_type]": applied.type } : {}),
            ...(applied.phase ? { "filter[phase]": applied.phase } : {}),
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
    if (form.type) next.set("type", form.type);
    if (form.phase) next.set("phase", form.phase);
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
            {t("search.filterType")}
            <select
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
              className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            >
              <option value="">{t("search.filterAny")}</option>
              {CONTRACT_TYPES.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </label>
          <label className="text-sm text-ink">
            {t("search.filterPhase")}
            <select
              value={form.phase}
              onChange={(e) => setForm({ ...form, phase: e.target.value })}
              className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            >
              <option value="">{t("search.filterAny")}</option>
              {PHASES_FILTER.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
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
          {activeFilters > 0 && (
            <button
              type="button"
              className="text-sm text-accent underline"
              onClick={() => {
                const cleared = { ...form, organisme: "", type: "", phase: "",
                  amount_min: "", amount_max: "", from: "", to: "" };
                setForm(cleared);
                const next = new URLSearchParams();
                if (cleared.q) next.set("q", cleared.q);
                setParams(next);
              }}
            >
              {t("search.clearFilters", { count: String(activeFilters) })}
            </button>
          )}
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
