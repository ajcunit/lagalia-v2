import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { api } from "../../api/client";
import { Badge, Button, EmptyState } from "../../components/ui";
import { t } from "../../i18n";

const EXAMPLES = [
  "Quants contractes tenim i quina és l'evolució per any dels imports adjudicats?",
  "Quins són els 10 adjudicataris amb més import acumulat?",
  "Hi ha red flags actius? Resumeix-los.",
  "Quants contractes de serveis es van publicar el 2025?",
];

export function Analyst() {
  const [question, setQuestion] = useState("");

  const ask = useMutation({
    mutationFn: async (q: string) => {
      const { data, error } = await api.POST("/ai/analyses", { body: { question: q } });
      if (error !== undefined) throw error;
      return data;
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
      {ask.data && (
        <div className="mt-4 space-y-3">
          <pre className="whitespace-pre-wrap rounded-lg border border-line bg-surface-raised p-4 text-sm text-ink shadow-card">
            {ask.data.answer_markdown}
          </pre>
          {ask.data.steps.length > 0 && (
            <details className="rounded-lg border border-line bg-surface-raised p-3 shadow-card">
              <summary className="cursor-pointer text-sm font-medium text-ink">
                {t("analyst.steps", { count: String(ask.data.steps.length) })}
              </summary>
              <div className="mt-2 space-y-3">
                {ask.data.steps.map((step, index) => (
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
          <p className="text-xs text-muted">{t("analyst.disclaimer")}</p>
        </div>
      )}
    </div>
  );
}
