import type { TranslationKey } from "../i18n/ca";

export interface ChecklistItem {
  labelKey: TranslationKey;
  ok: boolean;
}

/** Rèplica UX de la política del backend (l'autoritat és el servidor). */
export function passwordChecklist(password: string): ChecklistItem[] {
  return [
    { labelKey: "setup.password.length", ok: password.length >= 12 },
    { labelKey: "setup.password.upper", ok: /[A-ZÀ-Ý]/.test(password) },
    { labelKey: "setup.password.lower", ok: /[a-zà-ý]/.test(password) },
    { labelKey: "setup.password.digit", ok: /\d/.test(password) },
  ];
}

export function passwordSatisfies(password: string): boolean {
  return passwordChecklist(password).every((item) => item.ok);
}
