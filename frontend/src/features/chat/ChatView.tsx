import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Button, EmptyState, Skeleton } from "../../components/ui";
import { Markdown } from "../../components/Markdown";
import { Plus, SendHorizonal, Trash2 } from "lucide-react";

import { t } from "../../i18n";
import { streamNdjson } from "../../lib/stream";

type Thread = components["schemas"]["ChatThread"];
type Message = components["schemas"]["ChatMessage"];

interface LiveState {
  answer: string;
  thinkingChars: number;
  steps: string[];
  sources: { title?: string | null; doc_type?: string | null }[];
}

const EMPTY_LIVE: LiveState = { answer: "", thinkingChars: 0, steps: [], sources: [] };

/** Conversa multi-torn amb streaming (specs/chat.md). Compartit entre el xat
 * general (/chat) i la pestanya Xat de la fitxa d'un contracte. */
export function ChatView(props: { scope: "general" | "contract"; contractId?: number }) {
  const queryClient = useQueryClient();
  const [threadId, setThreadId] = useState<number | null>(null);
  const [input, setInput] = useState("");
  const [live, setLive] = useState<LiveState>(EMPTY_LIVE);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const threadsKey = ["chat-threads", props.scope, props.contractId ?? null];
  const threads = useQuery({
    queryKey: threadsKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/chat/threads", {
        params: {
          query: {
            scope: props.scope,
            ...(props.contractId ? { contract_id: props.contractId } : {}),
          },
        },
      });
      if (error !== undefined) throw error;
      return data.data;
    },
  });
  const activeId = threadId ?? threads.data?.[0]?.id ?? null;

  const conversation = useQuery({
    queryKey: ["chat-thread", activeId],
    enabled: activeId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET("/chat/threads/{id}", {
        params: { path: { id: activeId! } },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });

  const createThread = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/chat/threads", {
        body: {
          scope: props.scope,
          ...(props.contractId ? { contract_id: props.contractId } : {}),
        },
      });
      if (error !== undefined) throw error;
      return data as Thread;
    },
    onSuccess: (thread) => {
      setThreadId(thread.id);
      void queryClient.invalidateQueries({ queryKey: threadsKey });
    },
  });

  const removeThread = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.DELETE("/chat/threads/{id}", {
        params: { path: { id } },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: (_data, id) => {
      if (activeId === id) setThreadId(null);
      void queryClient.invalidateQueries({ queryKey: threadsKey });
    },
  });

  const send = useMutation({
    mutationFn: async (content: string) => {
      let id = activeId;
      if (id === null) {
        const created = await createThread.mutateAsync();
        id = created.id;
      }
      setPendingQuestion(content);
      setLive(EMPTY_LIVE);
      let failed: string | null = null;
      await streamNdjson(`/chat/threads/${id}/messages/stream`, { content }, (event) => {
        if (event.type === "delta")
          setLive((prev) => ({ ...prev, answer: prev.answer + String(event.text ?? "") }));
        if (event.type === "thinking")
          setLive((prev) => ({
            ...prev,
            thinkingChars: prev.thinkingChars + String(event.text ?? "").length,
          }));
        if (event.type === "step")
          setLive((prev) => ({ ...prev, steps: [...prev.steps, String(event.tool ?? "")] }));
        if (event.type === "sources")
          setLive((prev) => ({
            ...prev,
            sources: (event.sources ?? []) as LiveState["sources"],
          }));
        if (event.type === "error") failed = String(event.detail ?? "error");
      });
      if (failed !== null) throw new Error(failed);
    },
    onSuccess: () => {
      setInput("");
      setPendingQuestion(null);
      setLive(EMPTY_LIVE);
      void queryClient.invalidateQueries({ queryKey: ["chat-thread", activeId] });
      void queryClient.invalidateQueries({ queryKey: threadsKey });
    },
  });

  const messages: Message[] = conversation.data?.messages ?? [];
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, live.answer, pendingQuestion]);

  function submit() {
    const content = input.trim();
    if (content.length >= 2 && !send.isPending) send.mutate(content);
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
      <aside>
        <Button tone="accent" onClick={() => createThread.mutate()} disabled={createThread.isPending}>
          <Plus className="mr-1 inline h-3.5 w-3.5 -translate-y-px" aria-hidden />
          {t("chat.newThread")}
        </Button>
        {threads.isPending ? (
          <Skeleton rows={4} />
        ) : (
          <ul className="mt-3 space-y-1">
            {(threads.data ?? []).map((thread) => (
              <li key={thread.id} className="group flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setThreadId(thread.id)}
                  aria-current={activeId === thread.id}
                  className={`min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-left text-sm ${
                    activeId === thread.id
                      ? "bg-accent-soft font-medium text-ink"
                      : "text-muted hover:bg-surface hover:text-ink"
                  }`}
                >
                  {thread.title ?? t("chat.untitled")}
                </button>
                <button
                  type="button"
                  aria-label={t("chat.deleteThread")}
                  className="invisible text-muted hover:text-danger group-hover:visible"
                  onClick={() => {
                    if (window.confirm(t("chat.deleteConfirm"))) removeThread.mutate(thread.id);
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <section className="flex min-h-[420px] flex-col rounded-lg border border-line bg-surface-raised shadow-card">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 && pendingQuestion === null ? (
            <EmptyState
              icon="💬"
              title={t(props.scope === "contract" ? "chat.emptyContract" : "chat.emptyGeneral")}
              detail={t("chat.emptyDetail")}
            />
          ) : (
            <>
              {messages.map((message) => (
                <ChatBubble
                  key={message.id}
                  role={message.role}
                  content={message.content}
                  sources={message.sources as LiveState["sources"] | null}
                />
              ))}
              {pendingQuestion !== null && (
                <>
                  <ChatBubble role="user" content={pendingQuestion} sources={null} />
                  {live.answer ? (
                    <ChatBubble role="assistant" content={live.answer} sources={live.sources} streaming />
                  ) : (
                    <p className="animate-pulse text-sm text-muted" role="status">
                      {live.thinkingChars > 0
                        ? t("analyst.thinkingLive", { chars: String(live.thinkingChars) })
                        : live.steps.length > 0
                          ? t("analyst.working", { tool: live.steps[live.steps.length - 1] ?? "" })
                          : t("analyst.thinking")}
                    </p>
                  )}
                </>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>
        {send.isError && (
          <p className="px-4 pb-1 text-sm text-danger">{t("chat.error")}</p>
        )}
        <form
          className="flex items-end gap-2 border-t border-line p-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={2}
            maxLength={4000}
            placeholder={t(
              props.scope === "contract" ? "chat.placeholderContract" : "chat.placeholderGeneral",
            )}
            aria-label={t("chat.inputLabel")}
            className="min-w-0 flex-1 resize-none rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          />
          <Button tone="accent" disabled={send.isPending || input.trim().length < 2} onClick={submit}>
            <SendHorizonal className="h-4 w-4" aria-hidden />
            <span className="sr-only">{t("chat.send")}</span>
          </Button>
        </form>
        <p className="px-4 pb-2 text-xs text-muted">{t("chat.disclaimer")}</p>
      </section>
    </div>
  );
}

function ChatBubble(props: {
  role: string;
  content: string;
  sources: { title?: string | null; doc_type?: string | null }[] | null;
  streaming?: boolean;
}) {
  const isUser = props.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          isUser ? "bg-accent-soft text-ink" : "bg-surface text-ink"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{props.content}</p>
        ) : (
          <>
            <Markdown>{props.content}</Markdown>
            {props.streaming && <span className="animate-pulse text-muted">▍</span>}
          </>
        )}
        {(props.sources ?? []).length > 0 && (
          <p className="mt-1.5 border-t border-line/60 pt-1 text-xs text-muted">
            {t("chat.sources")}:{" "}
            {(props.sources ?? [])
              .map((source) => source.title)
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
      </div>
    </div>
  );
}
