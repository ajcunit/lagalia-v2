import { ca, type TranslationKey } from "./ca";

/**
 * Traducció mínima tipada: t("clau", { var: valor }).
 * Un sol catàleg (ca) de moment; la infraestructura ja separa claus de textos.
 */
export function t(
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  const template: string = ca[key];
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}
