import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { Bot } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { SheetTabs } from "../../components/contractSheet";
import { t } from "../../i18n";
import { ca } from "../../i18n/ca";
import { formatDateTime } from "../../lib/format";
import { Markdown } from "../../components/Markdown";

type Provider = components["schemas"]["AiProvider"];
type Protocol = Provider["protocol"];

function ProviderCard(props: { provider: Provider }) {
  const queryClient = useQueryClient();
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["ai-providers"] });
  const p = props.provider;
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(p.default_model ?? "");
  const [health, setHealth] = useState<string | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);

  const test = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/ai/providers/{id}/actions/test-completion", {
        params: { path: { id: p.id } },
        body: { prompt },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: (result) => {
      setAnswer(
        result.status === "ok"
          ? `${result.content ?? ""}

[${result.model ?? ""} · ${String(result.input_tokens ?? "?")}/${String(result.output_tokens ?? "?")} tokens]`
          : t("ai.testError", { detail: result.detail ?? "" }),
      );
      void queryClient.invalidateQueries({ queryKey: ["ai-runs"] });
    },
    onError: () => setAnswer(t("ai.testError", { detail: "" })),
  });

  const patch = useMutation({
    mutationFn: async (body: { enabled?: boolean; default_model?: string }) => {
      const { error } = await api.PATCH("/ai/providers/{id}", {
        params: { path: { id: p.id } },
        body,
      });
      if (error !== undefined) throw error;
    },
    onSuccess: invalidate,
  });
  const putKey = useMutation({
    mutationFn: async () => {
      const { error } = await api.PUT("/ai/providers/{id}/api-key", {
        params: { path: { id: p.id } },
        body: { api_key: apiKey },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => {
      setApiKey("");
      invalidate();
    },
  });
  const check = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/ai/providers/{id}/actions/healthcheck", {
        params: { path: { id: p.id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: (result) => {
      setHealth(result.detail ? `${result.status}: ${result.detail}` : result.status);
      setModels(result.models);
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE("/ai/providers/{id}", { params: { path: { id: p.id } } });
      if (error !== undefined) throw error;
    },
    onSuccess: invalidate,
  });

  return (
    <SectionCard title={`${p.name} (${p.protocol})`}>
      <div className="flex flex-wrap items-center gap-2">
        {p.enabled ? (
          <Badge tone="accent">{t("webhooks.active")}</Badge>
        ) : (
          <Badge tone="danger">{t("webhooks.inactive")}</Badge>
        )}
        <code className="text-xs text-muted">{p.base_url}</code>
        {p.health_status && (
          <span className="text-sm text-muted">
            {t("config.health")}: {p.health_status}
            {p.last_health_check && ` (${formatDateTime(p.last_health_check)})`}
          </span>
        )}
        <span className="ml-auto flex gap-2">
          <Button disabled={patch.isPending} onClick={() => patch.mutate({ enabled: !p.enabled })}>
            {p.enabled ? t("webhooks.deactivate") : t("webhooks.activate")}
          </Button>
          <Button disabled={check.isPending} onClick={() => check.mutate()}>
            {t("config.checkHealth")}
          </Button>
          <Button
            tone="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(t("ai.confirmDelete", { name: p.name }))) remove.mutate();
            }}
          >
            ✕
          </Button>
        </span>
      </div>
      {health && <p className="mt-2 rounded-md bg-accent-soft p-2 text-sm text-ink">{health}</p>}
      {models.length > 0 && (
        <p className="mt-1 text-xs text-muted">
          {t("ai.modelsDetected")}: {models.slice(0, 12).join(", ")}
          {models.length > 12 ? "…" : ""}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-sm text-ink">
          {t("ai.defaultModel")}
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="mt-1 block w-56 rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-sm"
          />
        </label>
        <Button
          disabled={patch.isPending || model === (p.default_model ?? "")}
          onClick={() => patch.mutate({ default_model: model })}
        >
          {t("admin.save")}
        </Button>
        <label className="text-sm text-ink">
          {t("ai.apiKey")} {p.api_key_set && <Badge tone="accent">{t("config.credentialSet")}</Badge>}
          <input
            type="password"
            autoComplete="new-password"
            value={apiKey}
            placeholder={p.api_key_set ? "••••••••" : t("config.credentialEmpty")}
            onChange={(e) => setApiKey(e.target.value)}
            className="mt-1 block w-64 rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-sm"
          />
        </label>
        <Button tone="accent" disabled={putKey.isPending || !apiKey} onClick={() => putKey.mutate()}>
          {t("config.saveCredentials")}
        </Button>
      </div>
      <div className="mt-4 border-t border-line pt-3">
        <label className="block text-sm font-medium text-ink">
          {t("ai.testPrompt")}
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            maxLength={2000}
            placeholder={t("ai.testPlaceholder")}
            className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
        <div className="mt-2">
          <Button tone="accent" disabled={test.isPending || !prompt.trim()} onClick={() => test.mutate()}>
            {test.isPending ? t("ai.testing") : t("ai.test")}
          </Button>
        </div>
        {answer && (
          <div className="mt-2 max-h-64 overflow-auto rounded-md bg-surface p-3">
            <Markdown>{answer}</Markdown>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function NewProviderForm() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [protocol, setProtocol] = useState<Protocol>("openai_compatible");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");

  const create = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/ai/providers", {
        body: {
          name,
          protocol,
          base_url: baseUrl,
          default_model: model || null,
        },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => {
      setName("");
      setBaseUrl("");
      setModel("");
      void queryClient.invalidateQueries({ queryKey: ["ai-providers"] });
    },
  });

  return (
    <form
      className="flex flex-wrap items-end gap-2 rounded-md border border-line bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (name && baseUrl) create.mutate();
      }}
    >
      <label className="text-sm text-ink">
        {t("ai.name")}
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100}
          placeholder="Ollama local" className="mt-1 block w-44 rounded-md border border-line bg-surface px-2 py-1.5 text-sm" />
      </label>
      <label className="text-sm text-ink">
        {t("ai.protocol")}
        <select value={protocol} onChange={(e) => setProtocol(e.target.value as Protocol)}
          className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm">
          <option value="openai_compatible">OpenAI-compatible (OpenAI, vLLM, OpenRouter…)</option>
          <option value="ollama">Ollama (natiu)</option>
          <option value="claude">Claude (Anthropic)</option>
          <option value="gemini">Gemini (Google)</option>
        </select>
      </label>
      <label className="min-w-64 flex-1 text-sm text-ink">
        {t("ai.baseUrl")}
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required
          placeholder={
            protocol === "claude"
              ? "https://api.anthropic.com"
              : protocol === "gemini"
                ? "https://generativelanguage.googleapis.com"
                : protocol === "ollama"
                  ? "http://localhost:11434"
                  : "http://localhost:8000/v1"
          }
          className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-sm" />
      </label>
      <label className="text-sm text-ink">
        {t("ai.defaultModel")}
        <input value={model} onChange={(e) => setModel(e.target.value)} maxLength={200}
          placeholder={
            protocol === "claude"
              ? "claude-sonnet-5"
              : protocol === "gemini"
                ? "gemini-2.5-flash"
                : "llama3"
          }
          className="mt-1 block w-48 rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-sm" />
      </label>
      <Button tone="accent" disabled={create.isPending || !name || !baseUrl} onClick={() => create.mutate()}>
        {t("ai.add")}
      </Button>
    </form>
  );
}

type TaskRow = {
  task: string;
  description: string;
  config: { provider_profile_id: number; model: string | null; max_tokens: number | null } | null;
  effective: { profile_id: number; profile_name: string; model: string | null } | null;
};

function TaskConfigRow(props: { row: TaskRow; providers: Provider[] }) {
  const queryClient = useQueryClient();
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["ai-tasks"] });
  const r = props.row;
  const [profileId, setProfileId] = useState<number | "">(r.config?.provider_profile_id ?? "");
  const [model, setModel] = useState(r.config?.model ?? "");

  const save = useMutation({
    mutationFn: async () => {
      const { error } = await api.PUT("/ai/tasks/{task}", {
        params: { path: { task: r.task } },
        body: { provider_profile_id: Number(profileId), model: model || null },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: invalidate,
  });
  const reset = useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE("/ai/tasks/{task}", {
        params: { path: { task: r.task } },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => {
      setProfileId("");
      setModel("");
      invalidate();
    },
  });

  const selected = props.providers.find((p) => p.id === profileId);
  return (
    <tr className="border-t border-line align-top">
      <td className="px-3 py-2">
        <p className="font-mono text-xs text-ink">{r.task}</p>
        <p className="text-xs text-muted">{r.description}</p>
      </td>
      <td className="px-3 py-2">
        <select
          value={profileId}
          onChange={(e) => setProfileId(e.target.value ? Number(e.target.value) : "")}
          aria-label={t("ai.taskProfile")}
          className="rounded-md border border-line bg-surface px-2 py-1 text-sm"
        >
          <option value="">{t("ai.taskDefault")}</option>
          {props.providers.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </td>
      <td className="px-3 py-2">
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={selected?.default_model ?? ""}
          aria-label={t("ai.model")}
          className="w-52 rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs"
        />
      </td>
      <td className="px-3 py-2 text-xs text-muted">
        {r.effective
          ? `${r.effective.profile_name} · ${r.effective.model ?? "—"}`
          : t("ai.taskUnresolved")}
        {r.config && r.effective && r.effective.profile_id !== r.config.provider_profile_id && (
          <span className="mt-0.5 block text-danger">{t("ai.taskFallbackWarning")}</span>
        )}
      </td>
      <td className="px-3 py-2">
        <span className="flex gap-1">
          <Button tone="accent" disabled={save.isPending || profileId === ""} onClick={() => save.mutate()}>
            {t("admin.save")}
          </Button>
          {r.config && (
            <Button disabled={reset.isPending} onClick={() => reset.mutate()}>
              {t("ai.taskReset")}
            </Button>
          )}
        </span>
      </td>
    </tr>
  );
}

function RagPanel() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const status = useQuery({
    queryKey: ["rag-status"],
    queryFn: async () => {
      const { data, error } = await api.GET("/rag/status");
      if (error !== undefined) throw error;
      return data;
    },
    refetchInterval: (q) => {
      const job = q.state.data?.last_job as { status?: string } | null | undefined;
      return job && (job.status === "running" || job.status === "queued") ? 2000 : false;
    },
  });
  const lastJob = status.data?.last_job as
    | { status?: string; progress?: number; progress_message?: string | null }
    | null
    | undefined;
  const indexing = lastJob?.status === "running" || lastJob?.status === "queued";
  const index = useMutation({
    mutationFn: async () => {
      const { error, response } = await api.POST("/rag/actions/index", {});
      if (error !== undefined) throw Object.assign(new Error(), { status: response.status });
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["rag-status"] }),
  });
  const search = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/rag/search", { body: { query } });
      if (error !== undefined) throw error;
      return data.data as Record<string, unknown>[];
    },
  });

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold text-ink">{t("rag.title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("rag.intro")}</p>
      <div className="mt-2 rounded-lg border border-line bg-surface-raised p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-3 text-sm text-ink">
          {status.data && (
            <span>
              {t("rag.status", {
                indexed: String(status.data.indexed),
                documents: String(status.data.documents),
                chunks: String(status.data.chunks),
              })}
            </span>
          )}
          <span className="ml-auto">
            <Button disabled={index.isPending} onClick={() => index.mutate()}>
              {t("rag.index")}
            </Button>
          </span>
        </div>
        {index.isError && <p className="mt-1 text-xs text-danger">{t("rag.indexError")}</p>}
        {indexing && (
          <div className="mt-2" role="status" aria-live="polite">
            <div className="h-2 w-full overflow-hidden rounded-full bg-surface">
              <div
                className="h-2 rounded-full bg-accent transition-all duration-500"
                style={{ width: `${Math.max(2, lastJob?.progress ?? 0)}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-muted">
              {lastJob?.progress_message ?? t("rag.indexQueued")} · {lastJob?.progress ?? 0}%
            </p>
          </div>
        )}
        {!indexing && lastJob && (
          <p className="mt-1 text-xs text-muted">
            {t("rag.lastRun", {
              status: String(lastJob.status),
              message: lastJob.progress_message ?? "",
            })}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-line pt-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("rag.searchPlaceholder")}
            aria-label={t("rag.title")}
            className="min-w-64 flex-1 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
          <Button
            tone="accent"
            disabled={search.isPending || query.trim().length < 3}
            onClick={() => search.mutate()}
          >
            {search.isPending ? t("analyst.thinking") : t("rag.search")}
          </Button>
        </div>
        {search.isError && (
          <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
            {t("rag.searchError")}
          </p>
        )}
        {search.data && (
          <div className="mt-2 space-y-2">
            {search.data.length === 0 ? (
              <p className="text-sm text-muted">{t("rag.searchEmpty")}</p>
            ) : (
              search.data.map((row, i) => (
                <div key={i} className="rounded-md bg-surface p-2">
                  <p className="text-xs text-muted">
                    {String(row.file_code ?? "—")} · {String(row.document_title ?? "")} ·{" "}
                    {String(row.doc_type ?? "")} ({String(row.phase ?? "")})
                  </p>
                  <p className="mt-1 line-clamp-4 text-sm text-ink">{String(row.content ?? "")}</p>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function LegalCorpusPanel() {
  const queryClient = useQueryClient();
  const norms = useQuery({
    queryKey: ["legal-norms"],
    queryFn: async () => {
      const { data, error } = await api.GET("/legal/norms");
      if (error !== undefined) throw error;
      return data.data as Record<string, unknown>[];
    },
  });
  const sync = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/legal/norms/actions/sync", {});
      if (error !== undefined) throw error;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["legal-norms"] }),
  });

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold text-ink">{t("legal.title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("legal.intro")}</p>
      <div className="mt-2 rounded-lg border border-line bg-surface-raised p-4 shadow-card">
        <div className="flex flex-wrap items-center gap-2">
          <span className="ml-auto">
            <Button disabled={sync.isPending} onClick={() => sync.mutate()}>
              {t("legal.sync")}
            </Button>
          </span>
        </div>
        {norms.isPending ? (
          <Skeleton rows={2} />
        ) : (norms.data ?? []).length === 0 ? (
          <p className="text-sm text-muted">{t("legal.empty")}</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="py-1 pr-3 font-medium">{t("legal.norm")}</th>
                <th scope="col" className="py-1 pr-3 font-medium">{t("legal.version")}</th>
                <th scope="col" className="py-1 pr-3 font-medium">{t("legal.articles")}</th>
                <th scope="col" className="py-1 font-medium">{t("legal.lastCheck")}</th>
              </tr>
            </thead>
            <tbody>
              {(norms.data ?? []).map((n, i) => (
                <tr key={i} className="border-t border-line align-top">
                  <td className="py-1.5 pr-3">
                    <span className="block text-ink">{String(n.title ?? "")}</span>
                    <code className="text-xs text-muted">{String(n.boe_id ?? "")}</code>
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs">
                    {String(n.consolidated_version ?? "—")}
                  </td>
                  <td className="py-1.5 pr-3">
                    {String(n.articles_count ?? 0)} · {String(n.chunks ?? 0)} frag.
                  </td>
                  <td className="py-1.5 text-xs text-muted">
                    {n.last_checked_at ? formatDateTime(String(n.last_checked_at)) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function AiAdmin() {
  const [tab, setTab] = useState("proveidors");
  const providers = useQuery({
    queryKey: ["ai-providers"],
    queryFn: async () => {
      const { data, error } = await api.GET("/ai/providers");
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const tasks = useQuery({
    queryKey: ["ai-tasks"],
    queryFn: async () => {
      const { data, error } = await api.GET("/ai/tasks");
      if (error !== undefined) throw error;
      return data.data as TaskRow[];
    },
  });
  const runs = useQuery({
    queryKey: ["ai-runs"],
    queryFn: async () => {
      const { data, error } = await api.GET("/ai/runs", {
        params: { query: { "page[size]": 25 } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  return (
    <div>
      <PageHeader
          backTo="/admin"
          icon={Bot} title={t("ai.title")} subtitle={t("ai.intro")} />

      <div className="mt-4">
        <SheetTabs
          tabs={[
            { key: "proveidors", label: t("ai.tabProviders") },
            { key: "tasques", label: t("ai.tabTasks") },
            { key: "rag", label: "RAG" },
            { key: "boe", label: t("ai.tabBoe") },
            { key: "execucions", label: t("ai.runs") },
          ]}
          active={tab}
          onSelect={setTab}
        />
      </div>

      {tab === "proveidors" && (
      <>
      <div className="mt-4"><NewProviderForm /></div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {providers.isPending ? (
          <Skeleton rows={6} />
        ) : providers.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (providers.data ?? []).length === 0 ? (
          <EmptyState icon="🤖" title={t("ai.empty")} detail={t("ai.emptyDetail")} />
        ) : (
          (providers.data ?? []).map((provider) => (
            <ProviderCard key={provider.id} provider={provider} />
          ))
        )}
      </div>

      </>
      )}

      {tab === "tasques" && (
      <>
      <h2 className="mt-4 text-lg font-semibold text-ink">{t("ai.tasksTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{t("ai.tasksIntro")}</p>
      <div className="mt-2 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {tasks.isPending ? (
          <div className="p-4"><Skeleton rows={2} /></div>
        ) : tasks.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.task")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.taskProfile")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.model")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.taskEffective")}</th>
                <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">{t("admin.save")}</span></th>
              </tr>
            </thead>
            <tbody>
              {(tasks.data ?? []).map((row) => (
                <TaskConfigRow key={row.task} row={row} providers={providers.data ?? []} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      </>
      )}

      {tab === "rag" && (
      <div className="space-y-6">
        <RagPanel />
        <PhasesPanel />
      </div>
      )}

      {tab === "boe" && <LegalCorpusPanel />}

      {tab === "execucions" && (
      <>
      <h2 className="mt-4 text-lg font-semibold text-ink">{t("ai.runs")}</h2>
      <div className="mt-2 overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
        {runs.isPending ? (
          <div className="p-4"><Skeleton rows={3} /></div>
        ) : runs.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (runs.data?.data ?? []).length === 0 ? (
          <EmptyState icon="🧾" title={t("ai.runsEmpty")} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.when")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.task")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.model")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.tokens")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("ai.latency")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("audit.col.success")}</th>
              </tr>
            </thead>
            <tbody>
              {(runs.data?.data ?? []).map((run: Record<string, unknown>, index: number) => (
                <tr key={index} className="border-t border-line">
                  <td className="whitespace-nowrap px-3 py-1.5">
                    {formatDateTime(String(run.created_at))}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-xs">{String(run.task)}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">{String(run.model ?? "—")}</td>
                  <td className="px-3 py-1.5 font-mono text-xs">
                    {String(run.input_tokens ?? "—")} / {String(run.output_tokens ?? "—")}
                  </td>
                  <td className="px-3 py-1.5">{run.latency_ms != null ? `${String(run.latency_ms)} ms` : "—"}</td>
                  <td className="px-3 py-1.5">
                    {run.status === "success" ? (
                      <Badge tone="accent">OK</Badge>
                    ) : (
                      <Badge tone="danger">{String(run.error_detail ?? "error")}</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      </>
      )}
    </div>
  );
}

/** Tria de fases per al RAG (specs/rag-service.md): els documents de les
 * fases marcades es descarreguen i s'indexen; la resta es mostren a la fitxa
 * només amb l'enllaç al portal. */
function PhasesPanel() {
  const queryClient = useQueryClient();
  const [selection, setSelection] = useState<Set<string> | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const phases = useQuery({
    queryKey: ["rag-phases"],
    queryFn: async () => {
      const { data, error } = await api.GET("/rag/phases");
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const { data, error } = await api.GET("/settings");
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const saved = settings.data?.find((s) => s.key === "rag.indexable_phases");
  const savedList: string[] | null = Array.isArray(saved?.value)
    ? (saved?.value as string[])
    : null;
  const effective = selection ?? (savedList !== null ? new Set(savedList) : null);

  const save = useMutation({
    mutationFn: async (value: string[] | null) => {
      const { error } = await api.PUT("/settings/{key}", {
        params: { path: { key: "rag.indexable_phases" } },
        body: { value, is_secret: false },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => {
      setMessage(t("ai.phasesSaved"));
      setSelection(null);
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => setMessage(t("favorites.saveError")),
  });

  function phaseLabel(phase: string): string {
    const key = `search.phase.${phase}`;
    return key in ca ? ca[key as keyof typeof ca] : phase;
  }

  function toggle(phase: string) {
    const base = effective ?? new Set((phases.data ?? []).map((row) => row.phase));
    const next = new Set(base);
    if (next.has(phase)) next.delete(phase);
    else next.add(phase);
    setSelection(next);
  }

  return (
    <SectionCard title={t("ai.phasesTitle")}>
      <p className="text-sm text-muted">{t("ai.phasesIntro")}</p>
      {phases.isPending ? (
        <Skeleton rows={4} />
      ) : phases.isError ? (
        <EmptyState icon="⚠️" title={t("admin.loadError")} />
      ) : (
        <ul className="mt-4 space-y-2.5">
          {(phases.data ?? []).map((row) => {
            const checked = effective === null || effective.has(row.phase);
            return (
              <li key={row.phase} className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  id={`ragphase-${row.phase}`}
                  checked={checked}
                  onChange={() => toggle(row.phase)}
                  className="h-4 w-4"
                />
                <label htmlFor={`ragphase-${row.phase}`} className="min-w-0 flex-1">
                  <span className="font-medium text-ink">{phaseLabel(row.phase)}</span>
                  <span className="ml-2 text-xs text-muted">
                    {t("ai.phasesCounts", {
                      total: String(row.total),
                      copies: String(row.with_copy),
                      indexed: String(row.indexed),
                    })}
                  </span>
                </label>
                {!checked && (
                  <span className="text-xs text-muted">{t("ai.phasesLinkOnly")}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <div className="mt-4 flex items-center gap-3">
        <Button
          tone="accent"
          disabled={save.isPending || selection === null}
          onClick={() => save.mutate(selection === null ? null : [...selection])}
        >
          {t("admin.save")}
        </Button>
        <button
          type="button"
          className="text-xs text-accent underline"
          onClick={() => {
            setSelection(null);
            save.mutate(null);
          }}
        >
          {t("ai.phasesAll")}
        </button>
        {message && <span className="text-sm text-muted">{message}</span>}
      </div>
      <p className="mt-2 text-xs text-muted">{t("ai.phasesNote")}</p>
    </SectionCard>
  );
}
