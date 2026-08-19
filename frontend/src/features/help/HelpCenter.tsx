import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { CircleHelp, MessagesSquare, ShieldCheck } from "lucide-react";

import { api } from "../../api/client";
import { useAuth } from "../../auth/AuthProvider";
import { Markdown } from "../../components/Markdown";
import { PageHeader } from "../../components/PageHeader";
import { Badge, EmptyState, Skeleton } from "../../components/ui";
import { t } from "../../i18n";

/** Centre d'ajuda (specs/help-wiki.md): wiki de funcionament. Els articles
 *  d'administració només arriben als admins (el filtre és al servidor). */
export function HelpCenter() {
  const { permissions } = useAuth();
  const [active, setActive] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const chatAvailable =
    (permissions?.actions ?? []).includes("audit:run") &&
    !(permissions?.disabled_modules ?? []).includes("chat");

  const list = useQuery({
    queryKey: ["help"],
    staleTime: 10 * 60 * 1000,
    queryFn: async () => {
      const { data, error } = await api.GET("/help");
      if (error !== undefined) throw error;
      return data.data;
    },
  });

  const slug = active ?? list.data?.[0]?.slug ?? null;
  const article = useQuery({
    queryKey: ["help-article", slug],
    enabled: slug !== null,
    staleTime: 10 * 60 * 1000,
    queryFn: async () => {
      const { data, error } = await api.GET("/help/{slug}", {
        params: { path: { slug: slug as string } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  const filtered = (list.data ?? []).filter(
    (item) => !query.trim() || item.title.toLowerCase().includes(query.trim().toLowerCase()),
  );

  return (
    <div>
      <PageHeader icon={CircleHelp} title={t("help.title")} subtitle={t("help.intro")} />

      <div className="mt-5 grid gap-4 lg:grid-cols-[280px_1fr]">
        <div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("help.search")}
            aria-label={t("help.search")}
            className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
          <nav aria-label={t("help.title")} className="mt-3">
            {list.isPending ? (
              <Skeleton rows={8} />
            ) : list.isError ? (
              <EmptyState icon="⚠️" title={t("admin.loadError")} />
            ) : (
              <ul className="space-y-0.5">
                {filtered.map((item) => (
                  <li key={item.slug}>
                    <button
                      type="button"
                      onClick={() => setActive(item.slug)}
                      aria-current={item.slug === slug}
                      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${
                        item.slug === slug
                          ? "bg-accent-soft font-semibold text-accent"
                          : "text-ink hover:bg-surface-sunken"
                      }`}
                    >
                      <span className="min-w-0 flex-1 truncate">{item.title}</span>
                      {item.audience === "admin" && (
                        <ShieldCheck
                          aria-hidden
                          className="h-3.5 w-3.5 shrink-0 text-muted"
                        />
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </nav>

          {chatAvailable && (
            <div className="mt-4 rounded-lg border border-line bg-surface-raised p-3 shadow-card">
              <p className="text-sm text-muted">{t("help.chatHint")}</p>
              <Link
                to="/chat"
                className="mt-2 inline-flex items-center gap-2 text-sm font-medium text-accent underline-offset-2 hover:underline"
              >
                <MessagesSquare aria-hidden className="h-4 w-4" />
                {t("help.chatOpen")}
              </Link>
            </div>
          )}
        </div>

        <div className="min-w-0 rounded-lg border border-line bg-surface-raised p-6 shadow-card">
          {article.isPending && slug !== null ? (
            <Skeleton rows={10} />
          ) : article.data !== undefined ? (
            <article>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-semibold text-ink">{article.data.title}</h2>
                {article.data.audience === "admin" && (
                  <Badge tone="neutral">{t("help.adminOnly")}</Badge>
                )}
              </div>
              <div className="prose-sm mt-3 max-w-3xl">
                <Markdown>{article.data.body}</Markdown>
              </div>
            </article>
          ) : (
            <EmptyState icon="📖" title={t("help.pick")} />
          )}
        </div>
      </div>
    </div>
  );
}
