import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Badge, Button, EmptyState } from "../../components/ui";
import { Markdown } from "../../components/Markdown";
import { streamNdjson } from "../../lib/stream";
import { t } from "../../i18n";

const EXAMPLES = [
  "Quants contractes tenim i quina és l'evolució per any dels imports adjudicats?",
  "Quins són els 10 adjudicataris amb més import acumulat?",
  "Hi ha red flags actius? Resumeix-los.",
  "Quants contractes de serveis es van publicar el 2025?",
];

export function Analyst() {
  const [question, setQuestion] = useState("");

  const [steps, setSteps] = useState<{ tool: string; args: unknown; rows: unknown }[]>([]);
  const [answer, setAnswer] = useState("");
  const [thinkingChars, setThinkingChars] = useState(0);
  const ask = useMutation({
    mutationFn: async (q: string) => {
      setSteps([]);
      setAnswer("");
      setThinkingChars(0);
      let failed: string | null = null;
      await streamNdjson("/ai/analyses/stream", { question: q }, (event) => {
        if (event.type === "step") {
          setThinkingChars(0);
          setSteps((prev) => [
            ...prev,
            { tool: String(event.tool), args: event.args, rows: event.rows },
          ]);
        }
        if (event.type === "delta") setAnswer((prev) => prev + String(event.text ?? ""));
        if (event.type === "thinking")
          setThinkingChars((prev) => prev + String(event.text ?? "").length);
        if (event.type === "error") failed = String(event.detail ?? "error");
      });
      if (failed !== null) throw new Error(failed);
    },
  });

  function submit(q: string) {
    setQuestion(q);
    if (q.trim().length >= 5) ask.mutate(q);
  }

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight text-ink">{t("analyst.title")}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("analyst.intro")}</p>

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder={t("analyst.placeholder")}
          className="min-w-72 flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm shadow-sm"
        />
        <Button
          tone="accent"
          disabled={ask.isPending || question.trim().length < 5}
          onClick={() => ask.mutate(question)}
        >
          {ask.isPending ? t("analyst.thinking") : t("analyst.submit")}
        </Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted hover:text-ink"
            onClick={() => submit(example)}
          >
            {example}
          </button>
        ))}
      </div>

      {ask.isError && (
        <div className="mt-4">
          <EmptyState icon="⚠️" title={t("analyst.error")} />
        </div>
      )}
      {(steps.length > 0 || answer !== "" || ask.isPending) && (
        <div className="mt-4 space-y-3">
          {ask.isPending && answer === "" && (
            <p className="animate-pulse text-sm text-muted" role="status">
              {thinkingChars > 0
                ? t("analyst.thinkingLive", { chars: String(thinkingChars) })
                : steps.length > 0
                  ? t("analyst.working", { tool: steps[steps.length - 1]?.tool ?? "" })
                  : t("analyst.thinking")}
            </p>
          )}
          {answer !== "" && (
            <div className="rounded-lg border border-line bg-surface-raised p-4 shadow-card">
              <Markdown>{answer}</Markdown>
              {ask.isPending && <span className="animate-pulse text-muted">▍</span>}
            </div>
          )}
          {steps.length > 0 && (
            <details className="rounded-lg border border-line bg-surface-raised p-3 shadow-card">
              <summary className="cursor-pointer text-sm font-medium text-ink">
                {t("analyst.steps", { count: String(steps.length) })}
              </summary>
              <div className="mt-2 space-y-3">
                {steps.map((step, index) => (
                  <div key={index}>
                    <p className="text-xs text-muted">
                      <Badge tone="neutral">{step.tool}</Badge>{" "}
                      <code>{JSON.stringify(step.args)}</code>
                    </p>
                    <pre className="mt-1 max-h-48 overflow-auto rounded bg-surface p-2 text-xs">
                      {JSON.stringify(step.rows, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </details>
          )}
          {answer !== "" && <p className="text-xs text-muted">{t("analyst.disclaimer")}</p>}
        </div>
      )}
    </div>
  );
}
