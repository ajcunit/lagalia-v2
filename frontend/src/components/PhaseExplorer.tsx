import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { Button, Skeleton } from "./ui";
import { t } from "../i18n";
import { formatBytes } from "../lib/format";

/** Afegir un document extern a un projecte del generador, amb creació al vol. */
export function AddToProject(props: { title: string; downloadUrl: string; fileCode: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
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
  const createAndAdd = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/doc-projects", { body: { name: newName } });
      if (error !== undefined) throw error;
      await add.mutateAsync((data as { id: number }).id);
    },
    onSuccess: () => {
      setNewName("");
      void queryClient.invalidateQueries({ queryKey: ["doc-projects"] });
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
        <span className="absolute right-0 top-5 z-10 block w-64 rounded-md border border-line bg-surface-raised p-2 shadow-card">
          {(projects.data ?? []).map((project) => (
            <button
              key={project.id}
              type="button"
              disabled={add.isPending}
              className="block w-full rounded px-2 py-1 text-left text-sm text-ink hover:bg-accent-soft"
              onClick={() => add.mutate(project.id)}
            >
              {project.name}
            </button>
          ))}
          <span
            className={`flex gap-1 ${
              (projects.data ?? []).length > 0 ? "mt-1 border-t border-line pt-1.5" : ""
            }`}
          >
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={t("search.newProjectPlaceholder")}
              aria-label={t("search.newProjectPlaceholder")}
              className="min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs"
            />
            <Button
              tone="accent"
              disabled={createAndAdd.isPending || !newName.trim()}
              onClick={() => createAndAdd.mutate()}
            >
              {t("search.create")}
            </Button>
          </span>
        </span>
      )}
    </span>
  );
}

/** Explorador d'una fase: documents descarregables (amb ＋projecte), criteris i mesa. */
export function PhasePanel(props: { url: string; fileCode: string }) {
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
