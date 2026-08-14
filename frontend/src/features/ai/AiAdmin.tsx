import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, SectionCard, Skeleton } from "../../components/ui";
import { t } from "../../i18n";
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
  });
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
        {index.isSuccess && <p className="mt-1 text-xs text-muted">{t("rag.indexQueued")}</p>}
        {index.isError && <p className="mt-1 text-xs text-danger">{t("rag.indexError")}</p>}
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

export function AiAdmin() {
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
      <h1 className="text-2xl font-bold tracking-tight text-ink">{t("ai.title")}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("ai.intro")}</p>

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

      <h2 className="mt-8 text-lg font-semibold text-ink">{t("ai.tasksTitle")}</h2>
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

      <RagPanel />

      <h2 className="mt-8 text-lg font-semibold text-ink">{t("ai.runs")}</h2>
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
    </div>
  );
}
