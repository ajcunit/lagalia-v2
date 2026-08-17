import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Folder, FolderOpen, Star } from "lucide-react";

import { api } from "../api/client";
import { FileTypeIcon } from "./FileTypeIcon";
import { Button, Skeleton } from "./ui";
import { useFolders } from "../features/favorites/useFolders";
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
export function PhasePanel(props: { url: string; fileCode: string; documentsOnly?: boolean }) {
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
                <FileTypeIcon name={doc.title} />
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
      {!props.documentsOnly && criteria.length > 0 && (
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
      {!props.documentsOnly && committee.length > 0 && (
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

/** Desa un expedient extern a una carpeta de favorits (amb creació al vol). */
export function SaveToFolder(props: { fileCode: string }) {
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
        <Star className="mr-1 inline h-3.5 w-3.5 -translate-y-px" aria-hidden />
        {t("favorites.save")}
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


/** Carpetes de documents per fase (fitxa externa): una carpeta desplegable
 * per cada fase publicada; el contingut es carrega en obrir-la. */
export function PhaseFolders(props: {
  phases: { phase: string; url: string }[];
  fileCode: string;
}) {
  return (
    <ul className="space-y-2">
      {props.phases.map(({ phase, url }) => (
        <li key={phase}>
          <PhaseFolder phase={phase} url={url} fileCode={props.fileCode} />
        </li>
      ))}
    </ul>
  );
}

function PhaseFolder(props: { phase: string; url: string; fileCode: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border border-line bg-surface-raised">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium text-ink hover:bg-accent-soft"
      >
        <span aria-hidden>
          {open ? <FolderOpen className="h-4 w-4 text-accent" /> : <Folder className="h-4 w-4 text-muted" />}
        </span>
        {t(`search.phase.${props.phase}` as Parameters<typeof t>[0])}
      </button>
      {open && (
        <div className="border-t border-line px-3 py-3">
          <PhasePanel url={props.url} fileCode={props.fileCode} documentsOnly />
        </div>
      )}
    </div>
  );
}
