import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { Star } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatCurrency, formatDate } from "../../lib/format";
import { useFolders } from "./useFolders";

type Folder = components["schemas"]["FavoriteFolder"];
type FolderColor = NonNullable<components["schemas"]["FolderBody"]["color"]>;
type Favorite = components["schemas"]["Favorite"];

export const FOLDER_COLORS = [
  "blue",
  "green",
  "amber",
  "red",
  "purple",
  "pink",
  "teal",
  "gray",
] as const;

const COLOR_DOT: Record<string, string> = {
  blue: "bg-blue-500",
  green: "bg-green-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
  purple: "bg-purple-500",
  pink: "bg-pink-500",
  teal: "bg-teal-500",
  gray: "bg-gray-400",
};

function FolderForm(props: { folder?: Folder; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(props.folder?.name ?? "");
  const [description, setDescription] = useState(props.folder?.description ?? "");
  const [color, setColor] = useState<FolderColor>((props.folder?.color as FolderColor) ?? "blue");

  const save = useMutation({
    mutationFn: async () => {
      const body = { name, description: description || null, color };
      if (props.folder) {
        const { error } = await api.PATCH("/folders/{id}", {
          params: { path: { id: props.folder.id } },
          body,
        });
        if (error !== undefined) throw error;
      } else {
        const { error } = await api.POST("/folders", { body });
        if (error !== undefined) throw error;
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["folders"] });
      props.onDone();
    },
  });

  return (
    <form
      className="space-y-2 rounded-md border border-line bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) save.mutate();
      }}
    >
      <label className="block text-sm text-ink">
        {t("favorites.folderName")}
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={100}
          className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
        />
      </label>
      <label className="block text-sm text-ink">
        {t("favorites.folderDescription")}
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={500}
          className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
        />
      </label>
      <fieldset>
        <legend className="text-sm text-ink">{t("favorites.folderColor")}</legend>
        <div className="mt-1 flex gap-1.5">
          {FOLDER_COLORS.map((option) => (
            <button
              key={option}
              type="button"
              aria-label={option}
              aria-pressed={color === option}
              onClick={() => setColor(option)}
              className={`h-6 w-6 rounded-full ${COLOR_DOT[option]} ${
                color === option ? "ring-2 ring-accent ring-offset-2" : ""
              }`}
            />
          ))}
        </div>
      </fieldset>
      <div className="flex gap-2">
        <Button tone="accent" disabled={save.isPending} onClick={() => name.trim() && save.mutate()}>
          {t("admin.save")}
        </Button>
        <Button onClick={props.onDone}>{t("favorites.cancel")}</Button>
      </div>
    </form>
  );
}

function FavoriteCard(props: { favorite: Favorite; folderId: number }) {
  const queryClient = useQueryClient();
  const f = props.favorite;
  const rows = f.snapshot;
  const first = rows[0] ?? {};
  const [open, setOpen] = useState(false);

  const remove = useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE("/folders/{id}/favorites/{favorite_id}", {
        params: { path: { id: props.folderId, favorite_id: f.id } },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["favorites", props.folderId] });
      void queryClient.invalidateQueries({ queryKey: ["folders"] });
    },
  });

  const links = (first.links ?? {}) as Record<string, string>;
  const portal = links.enllac_perfil_contractant ?? links.enllac_publicacio;

  return (
    <article className="rounded-lg border border-line bg-surface-raised p-4 shadow-card">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-ink">{f.subject ?? f.file_code}</h3>
          <p className="mt-0.5 text-sm text-muted">{f.awarding_body}</p>
        </div>
        <div className="text-right text-sm">
          <p className="font-mono text-xs text-muted">{f.file_code}</p>
          <p className="text-muted">{f.published_at ? formatDate(f.published_at) : ""}</p>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        {typeof first.contract_type === "string" && <Badge tone="neutral">{first.contract_type}</Badge>}
        {typeof first.status === "string" && first.status && <Badge tone="accent">{first.status}</Badge>}
        <span className="ml-auto flex items-center gap-2">
          {portal && (
            <a href={portal} target="_blank" rel="noreferrer" className="text-xs text-accent underline">
              {t("search.openInPortal")}
            </a>
          )}
          <button type="button" className="text-xs text-muted underline" onClick={() => setOpen(!open)}>
            {open ? t("sync.hideDetails") : t("sync.showDetails")}
          </button>
          <Button
            tone="danger"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(t("favorites.confirmRemove"))) remove.mutate();
            }}
          >
            {t("favorites.remove")}
          </Button>
        </span>
      </div>
      {open && (
        <div className="mt-2 overflow-x-auto rounded-md bg-surface p-3 text-sm">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-muted">
                <th scope="col" className="py-1 pr-2 font-medium">{t("contracts.col.state")}</th>
                <th scope="col" className="py-1 pr-2 font-medium">Lot</th>
                <th scope="col" className="py-1 pr-2 font-medium">{t("search.budget")}</th>
                <th scope="col" className="py-1 pr-2 font-medium">{t("search.award")}</th>
                <th scope="col" className="py-1 font-medium">{t("search.contractor")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const contractor = (row.contractor ?? {}) as Record<string, unknown>;
                return (
                  <tr key={index} className="border-t border-line">
                    <td className="py-1 pr-2">{String(row.status ?? "—")}</td>
                    <td className="py-1 pr-2">{String(row.lot ?? "") || "—"}</td>
                    <td className="py-1 pr-2">
                      {row.budget_vat != null ? formatCurrency(String(row.budget_vat)) : "—"}
                    </td>
                    <td className="py-1 pr-2">
                      {row.award_amount != null ? formatCurrency(String(row.award_amount)) : "—"}
                    </td>
                    <td className="py-1">
                      {typeof contractor.name === "string" ? contractor.name : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">{t("favorites.snapshotNote")}</p>
        </div>
      )}
    </article>
  );
}

export function FavoritesPage() {
  const queryClient = useQueryClient();
  const folders = useFolders();
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState<"new" | Folder | null>(null);

  const folderList = folders.data?.data ?? [];
  const active = folderList.find((f) => f.id === selected) ?? folderList[0] ?? null;

  const favorites = useQuery({
    queryKey: ["favorites", active?.id],
    enabled: active !== null,
    queryFn: async () => {
      const { data, error } = await api.GET("/folders/{id}/favorites", {
        params: { path: { id: active!.id } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  const removeFolder = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.DELETE("/folders/{id}", { params: { path: { id } } });
      if (error !== undefined) throw error;
    },
    onSuccess: () => {
      setSelected(null);
      void queryClient.invalidateQueries({ queryKey: ["folders"] });
    },
  });

  return (
    <div>
      <PageHeader icon={Star} title={t("favorites.title")} subtitle={t("favorites.intro")} />

      <div className="mt-4 grid gap-4 lg:grid-cols-[280px_1fr]">
        <aside>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">{t("favorites.folders")}</h2>
            <Button onClick={() => setEditing("new")}>{t("favorites.newFolder")}</Button>
          </div>
          {editing === "new" && (
            <div className="mt-2">
              <FolderForm onDone={() => setEditing(null)} />
            </div>
          )}
          {folders.isPending ? (
            <Skeleton rows={4} />
          ) : folderList.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{t("favorites.noFolders")}</p>
          ) : (
            <ul className="mt-2 space-y-1">
              {folderList.map((folder) => (
                <li key={folder.id}>
                  {editing !== "new" && editing?.id === folder.id ? (
                    <FolderForm folder={folder} onDone={() => setEditing(null)} />
                  ) : (
                    <div
                      className={`flex items-center gap-2 rounded-md px-2 py-1.5 ${
                        active?.id === folder.id ? "bg-accent-soft" : "hover:bg-surface"
                      }`}
                    >
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 items-center gap-2 text-left"
                        onClick={() => setSelected(folder.id)}
                      >
                        <span
                          aria-hidden
                          className={`h-3 w-3 shrink-0 rounded-full ${COLOR_DOT[folder.color ?? "gray"]}`}
                        />
                        <span className="truncate text-sm text-ink">{folder.name}</span>
                        <span className="ml-auto text-xs text-muted">{folder.favorites_count}</span>
                      </button>
                      <button
                        type="button"
                        className="text-xs text-muted underline"
                        onClick={() => setEditing(folder)}
                      >
                        {t("favorites.edit")}
                      </button>
                      <button
                        type="button"
                        className="text-xs text-danger underline"
                        onClick={() => {
                          if (window.confirm(t("favorites.confirmDeleteFolder", { name: folder.name })))
                            removeFolder.mutate(folder.id);
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section aria-live="polite">
          {active === null ? (
            <EmptyState icon="⭐" title={t("favorites.emptyTitle")} detail={t("favorites.emptyDetail")} />
          ) : favorites.isPending ? (
            <Skeleton rows={6} />
          ) : favorites.isError ? (
            <EmptyState icon="⚠️" title={t("admin.loadError")} />
          ) : favorites.data.data.length === 0 ? (
            <EmptyState icon="⭐" title={t("favorites.folderEmpty")} detail={t("favorites.folderEmptyDetail")} />
          ) : (
            <div className="space-y-3">
              {favorites.data.data.map((favorite) => (
                <FavoriteCard key={favorite.id} favorite={favorite} folderId={active.id} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
