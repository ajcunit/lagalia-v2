/** Errors RFC 9457 de l'API, per mostrar-los amb títol humà i trace_id. */
export interface Problem {
  title: string;
  status: number;
  detail?: string;
  trace_id?: string;
  retryAfterSeconds?: number;
}

export function asProblem(error: unknown, response?: Response): Problem {
  const fallback: Problem = { title: "Error inesperat", status: response?.status ?? 0 };
  if (typeof error !== "object" || error === null) return fallback;
  const body = error as Record<string, unknown>;
  const retryAfter = response?.headers.get("Retry-After");
  return {
    title: typeof body.title === "string" ? body.title : fallback.title,
    status: typeof body.status === "number" ? body.status : fallback.status,
    detail: typeof body.detail === "string" ? body.detail : undefined,
    trace_id: typeof body.trace_id === "string" ? body.trace_id : undefined,
    retryAfterSeconds: retryAfter ? Number(retryAfter) : undefined,
  };
}
