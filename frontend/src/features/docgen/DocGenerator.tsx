import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { Markdown } from "../../components/Markdown";
import { streamNdjson } from "../../lib/stream";
import { getAccessToken } from "../../auth/session";
import { Layers } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";

type DocType = "PPT" | "PPA" | "REPORT";
type SectionField = { label: string; hint?: string; value: string };
type Section = {
  title: string;
  instructions: string;
  content_md: string;
  sources: { n?: number; file_code?: string | null; document_title?: string | null }[];
  fields?: SectionField[];
};
type Reference = { id: number; title: string | null; doc_type: string | null; file_code: string | null };

const DOC_TYPES: { key: DocType; label: string }[] = [
  { key: "PPT", label: "PPT" },
  { key: "PPA", label: "PPA" },
  { key: "REPORT", label: "Informe" },
];

function ReferencePicker(props: { projectId: number; references: Reference[] }) {
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const candidates = useQuery({
    queryKey: ["doc-references", q],
    enabled: q.trim().length >= 2,
    queryFn: async () => {
      const { data, error } = await api.GET("/doc-references", {
        params: { query: { q: q.trim() } },
      });
      if (error !== undefined) throw error;
      return data.data as Reference[];
    },
  });
  const save = useMutation({
    mutationFn: async (ids: number[]) => {
      const { error } = await api.PUT("/doc-projects/{id}/references", {
        params: { path: { id: props.projectId } },
        body: { document_ids: ids },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["doc-project", props.projectId] }),
  });
  const currentIds = props.references.map((r) => r.id);

  return (
    <div className="rounded-lg border border-line bg-surface-raised p-4 shadow-card">
      <h3 className="text-sm font-semibold text-ink">{t("docgen.references")}</h3>
      <p className="mt-1 text-xs text-muted">{t("docgen.referencesIntro")}</p>
      {props.references.length > 0 && (
        <ul className="mt-2 space-y-1">
          {props.references.map((ref) => (
            <li key={ref.id} className="flex items-center gap-2 text-sm text-ink">
              <code className="text-xs text-accent">{ref.file_code ?? "—"}</code>
              <span className="min-w-0 flex-1 truncate">{ref.title}</span>
              <button
                type="button"
                className="text-xs text-danger underline"
                onClick={() => save.mutate(currentIds.filter((id) => id !== ref.id))}
              >
                {t("favorites.remove")}
              </button>
            </li>
          ))}
        </ul>
      )}
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={t("docgen.searchReferences")}
        className="mt-2 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
      />
      {candidates.data && (
        <ul className="mt-1 space-y-1">
          {candidates.data
            .filter((c) => !currentIds.includes(c.id))
            .slice(0, 8)
            .map((c) => (
              <li key={c.id} className="flex items-center gap-2 text-sm">
                <code className="text-xs text-muted">{c.file_code ?? "—"}</code>
                <span className="min-w-0 flex-1 truncate text-ink">{c.title}</span>
                <Button disabled={save.isPending} onClick={() => save.mutate([...currentIds, c.id])}>
                  {t("docgen.add")}
                </Button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}

function SectionEditor(props: {
  projectId: number;
  docType: DocType;
  index: number;
  section: Section;
  onChange: (section: Section) => void;
}) {
  const s = props.section;
  const [drafting, setDrafting] = useState(false);
  const [thinking, setThinking] = useState(0);
  const [open, setOpen] = useState(false);

  async function draft() {
    setDrafting(true);
    setThinking(0);
    let acc = "";
    let localSources: Section["sources"] = s.sources ?? [];
    props.onChange({ ...s, content_md: "" });
    try {
      await streamNdjson(
        `/doc-projects/${props.projectId}/documents/${props.docType}/sections/${props.index}/actions/draft/stream`,
        { instructions: s.instructions || null, fields: s.fields ?? [] },
        (event) => {
          if (event.type === "sources") localSources = event.sources as Section["sources"];
          if (event.type === "delta") acc += String(event.text ?? "");
          if (event.type === "thinking") {
            setThinking((prev) => prev + String(event.text ?? "").length);
            return;
          }
          props.onChange({ ...s, content_md: acc, sources: localSources });
        },
      );
    } finally {
      setDrafting(false);
    }
  }

  return (
    <div className="rounded-lg border border-line bg-surface-raised p-3 shadow-card">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-expanded={open}
          className="w-5 text-muted"
          onClick={() => setOpen(!open)}
        >
          {open ? "▾" : "▸"}
        </button>
        <input
          value={s.title}
          onChange={(e) => props.onChange({ ...s, title: e.target.value })}
          className="min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1 py-0.5 text-sm font-semibold text-ink hover:border-line"
        />
        {s.content_md && <Badge tone="accent">{t("docgen.drafted")}</Badge>}
        <Button tone="accent" disabled={drafting} onClick={() => void draft()}>
          {drafting ? t("docgen.drafting") : t("docgen.draft")}
        </Button>
      </div>
      {drafting && !s.content_md && (
        <p className="mt-1 animate-pulse text-xs text-muted" role="status">
          {thinking > 0
            ? t("riskAudit.aiThinkingLive", { chars: String(thinking) })
            : t("docgen.retrieving")}
        </p>
      )}
      {(s.fields ?? []).length > 0 && (
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {(s.fields ?? []).map((field, fi) => (
            <label key={fi} className="text-sm text-ink">
              {field.label}
              <input
                value={field.value}
                onChange={(e) =>
                  props.onChange({
                    ...s,
                    fields: (s.fields ?? []).map((f, j) =>
                      j === fi ? { ...f, value: e.target.value } : f,
                    ),
                  })
                }
                placeholder={field.hint ?? ""}
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
          ))}
        </div>
      )}
      {open && (
        <div className="mt-2 space-y-2">
          <input
            value={s.instructions}
            onChange={(e) => props.onChange({ ...s, instructions: e.target.value })}
            placeholder={t("docgen.instructionsPlaceholder")}
            className="w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
          <textarea
            value={s.content_md}
            onChange={(e) => props.onChange({ ...s, content_md: e.target.value })}
            rows={8}
            className="w-full rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-xs"
          />
        </div>
      )}
      {s.content_md && (
        <div className="mt-2 rounded-md bg-surface p-3">
          <Markdown>{s.content_md}</Markdown>
          {drafting && <span className="animate-pulse text-muted">▍</span>}
        </div>
      )}
      {(s.sources ?? []).length > 0 && (
        <p className="mt-1 text-xs text-muted">
          {t("docgen.sources")}:{" "}
          {(s.sources ?? [])
            .map((src) => `[${src.n}] ${src.file_code ?? "?"} ${src.document_title ?? ""}`)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}

function ProjectView(props: { projectId: number; onBack: () => void }) {
  const queryClient = useQueryClient();
  const [docType, setDocType] = useState<DocType>("PPT");
  const [sections, setSections] = useState<Section[] | null>(null);

  const project = useQuery({
    queryKey: ["doc-project", props.projectId],
    queryFn: async () => {
      const { data, error } = await api.GET("/doc-projects/{id}", {
        params: { path: { id: props.projectId } },
      });
      if (error !== undefined) throw error;
      return data as {
        id: number;
        name: string;
        references: Reference[];
        documents: Record<string, Section[]>;
      };
    },
  });

  const currentSections: Section[] =
    sections ?? ((project.data?.documents[docType] ?? []) as Section[]);

  const generateIndex = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/doc-projects/{id}/documents/{doc_type}/actions/generate-index",
        { params: { path: { id: props.projectId, doc_type: docType } } },
      );
      if (error !== undefined) throw error;
      return (data as { sections: Section[] }).sections;
    },
    onSuccess: (result) => {
      setSections(result);
      void queryClient.invalidateQueries({ queryKey: ["doc-project", props.projectId] });
    },
  });
  const save = useMutation({
    mutationFn: async () => {
      const { error } = await api.PATCH("/doc-projects/{id}/documents/{doc_type}", {
        params: { path: { id: props.projectId, doc_type: docType } },
        body: { sections: currentSections as unknown as Record<string, unknown>[] },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["doc-project", props.projectId] }),
  });

  const [legalReview, setLegalReview] = useState("");
  const [legalArticles, setLegalArticles] = useState<{ article?: string; url?: string }[]>([]);
  const reviewLegal = useMutation({
    mutationFn: async () => {
      const separator = "\n\n";
      const body = currentSections
        .map((section) => ["## " + section.title, section.content_md].join(separator))
        .join(separator)
        .slice(0, 39000);
      setLegalReview("");
      setLegalArticles([]);
      await streamNdjson(
        "/compliance/review-text",
        { text: body, subject_type: "document" },
        (event) => {
          if (event.type === "articles")
            setLegalArticles(event.articles as { article?: string; url?: string }[]);
          if (event.type === "delta") setLegalReview((prev) => prev + String(event.text ?? ""));
        },
      );
    },
  });

  async function exportDocx() {
    const token = getAccessToken();
    const response = await fetch(
      `/api/v1/doc-projects/${props.projectId}/documents/${docType}/export.docx`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${docType}-${project.data?.name ?? "document"}.docx`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (project.isPending) return <Skeleton rows={8} />;
  if (project.isError) return <EmptyState icon="⚠️" title={t("admin.loadError")} />;

  return (
    <div>
      <PageHeader
        icon={Layers}
        title={project.data.name}
        actions={
          <Button onClick={props.onBack}>← {t("docgen.backToProjects")}</Button>
        }
      />
      <div className="mt-3"><ReferencePicker projectId={props.projectId} references={project.data.references} /></div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {DOC_TYPES.map((dt) => (
          <button
            key={dt.key}
            type="button"
            aria-pressed={docType === dt.key}
            onClick={() => {
              setDocType(dt.key);
              setSections(null);
            }}
            className={`rounded-full border px-3 py-1 text-sm ${
              docType === dt.key ? "border-accent bg-accent-soft text-ink" : "border-line text-muted"
            }`}
          >
            {dt.label}
          </button>
        ))}
        <span className="ml-auto flex gap-2">
          <Button disabled={generateIndex.isPending} onClick={() => generateIndex.mutate()}>
            {generateIndex.isPending ? t("docgen.indexing") : t("docgen.generateIndex")}
          </Button>
          <Button disabled={save.isPending} onClick={() => save.mutate()}>
            {t("admin.save")}
          </Button>
          <Button
            disabled={reviewLegal.isPending || currentSections.every((s) => !s.content_md)}
            onClick={() => reviewLegal.mutate()}
          >
            {reviewLegal.isPending ? t("docgen.reviewing") : t("docgen.reviewLegal")}
          </Button>
          <Button tone="accent" disabled={currentSections.length === 0} onClick={() => void exportDocx()}>
            {t("docgen.export")}
          </Button>
        </span>
      </div>

      {(legalReview || reviewLegal.isPending) && (
        <div className="mt-3 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card">
          <h3 className="text-sm font-semibold text-ink">{t("docgen.legalTitle")}</h3>
          {legalArticles.length > 0 && (
            <p className="mt-1 text-xs text-muted">
              {t("docgen.legalArticles")}:{" "}
              {legalArticles.map((a) => a.article).filter(Boolean).join(" · ")}
            </p>
          )}
          {legalReview ? (
            <div className="mt-2 max-h-96 overflow-auto rounded-md bg-surface p-3">
              <Markdown>{legalReview}</Markdown>
              {reviewLegal.isPending && <span className="animate-pulse text-muted">▍</span>}
            </div>
          ) : (
            <p className="mt-2 animate-pulse text-sm text-muted">{t("docgen.reviewing")}</p>
          )}
          <p className="mt-1 text-xs text-muted">{t("docgen.legalDisclaimer")}</p>
        </div>
      )}

      <div className="mt-3 space-y-3">
        {currentSections.length === 0 ? (
          <EmptyState icon="📄" title={t("docgen.noSections")} detail={t("docgen.noSectionsDetail")} />
        ) : (
          currentSections.map((section, index) => (
            <SectionEditor
              key={index}
              projectId={props.projectId}
              docType={docType}
              index={index}
              section={section}
              onChange={(updated) =>
                setSections((prev) => {
                  const base =
                    prev ?? ((project.data?.documents[docType] ?? []) as Section[]);
                  return base.map((s, i) => (i === index ? updated : s));
                })
              }
            />
          ))
        )}
      </div>
    </div>
  );
}

export function DocGenerator() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [name, setName] = useState("");

  const projects = useQuery({
    queryKey: ["doc-projects"],
    queryFn: async () => {
      const { data, error } = await api.GET("/doc-projects");
      if (error !== undefined) throw error;
      return data.data as { id: number; name: string; references: number }[];
    },
  });
  const create = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/doc-projects", { body: { name } });
      if (error !== undefined) throw error;
      return data as { id: number };
    },
    onSuccess: (result) => {
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["doc-projects"] });
      setSelected(result.id);
    },
  });
  const remove = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.DELETE("/doc-projects/{id}", { params: { path: { id } } });
      if (error !== undefined) throw error;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["doc-projects"] }),
  });

  if (selected !== null) {
    return (
      <div>
        <ProjectView projectId={selected} onBack={() => setSelected(null)} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader icon={Layers} title={t("docgen.title")} subtitle={t("docgen.intro")} />

      <form
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <label className="min-w-64 flex-1 text-sm text-ink">
          {t("docgen.projectName")}
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            placeholder={t("docgen.projectPlaceholder")}
            className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
        <Button tone="accent" disabled={create.isPending || !name.trim()} onClick={() => create.mutate()}>
          {t("docgen.create")}
        </Button>
      </form>

      <div className="mt-4 space-y-2">
        {projects.isPending ? (
          <Skeleton rows={4} />
        ) : projects.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (projects.data ?? []).length === 0 ? (
          <EmptyState icon="📄" title={t("docgen.empty")} detail={t("docgen.emptyDetail")} />
        ) : (
          (projects.data ?? []).map((project) => (
            <div
              key={project.id}
              className="flex items-center gap-2 rounded-lg border border-line bg-surface-raised p-3 shadow-card"
            >
              <button
                type="button"
                className="min-w-0 flex-1 truncate text-left text-sm font-medium text-ink hover:text-accent"
                onClick={() => setSelected(project.id)}
              >
                {project.name}
              </button>
              <span className="text-xs text-muted">
                {t("docgen.referencesCount", { count: String(project.references) })}
              </span>
              <button
                type="button"
                className="text-xs text-danger underline"
                onClick={() => {
                  if (window.confirm(t("docgen.confirmDelete", { name: project.name })))
                    remove.mutate(project.id);
                }}
              >
                ✕
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
