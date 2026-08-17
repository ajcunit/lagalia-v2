/** Ordre canònic de fases del portal (02 §2.10). */
export const PHASE_ORDER = [
  "futura",
  "agregada",
  "cpm",
  "previ",
  "licitacio",
  "avaluacio",
  "adjudicacio",
  "formalitzacio",
  "anulacio",
] as const;

export type PhaseKey = (typeof PHASE_ORDER)[number];

export function phasesFromUrls(
  urls: Record<string, unknown> | null | undefined,
): { phase: PhaseKey; url: string }[] {
  const map = urls ?? {};
  return PHASE_ORDER.flatMap((phase) => {
    const url = map[phase];
    return typeof url === "string" && url ? [{ phase, url }] : [];
  });
}
