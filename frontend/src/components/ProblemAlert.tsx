import type { Problem } from "../api/problem";
import { t } from "../i18n";

/** Error d'API amb títol humà, detall i trace_id copiable (10-ui.md §5). */
export function ProblemAlert({ problem }: { problem: Problem | null }) {
  return (
    <div aria-live="assertive" role="alert" className="min-h-6">
      {problem && (
        <div className="rounded-md border border-danger/40 bg-surface-raised p-3 text-sm shadow-card">
          <p className="font-medium text-danger">{problem.title}</p>
          {problem.detail && <p className="mt-1 text-muted">{problem.detail}</p>}
          {problem.retryAfterSeconds !== undefined && (
            <p className="mt-1 text-muted">
              {t("common.retryIn", { seconds: problem.retryAfterSeconds })}
            </p>
          )}
          {problem.trace_id && (
            <p className="mt-1 font-mono text-xs text-muted select-all">
              {t("common.traceId", { traceId: problem.trace_id })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
