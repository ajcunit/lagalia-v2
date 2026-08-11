import { t } from "../i18n";
import { useTheme } from "../theme/useTheme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const label = theme === "dark" ? t("theme.light") : t("theme.dark");
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={t("theme.toggle")}
      title={label}
      className="rounded-md border border-line bg-surface-raised px-3 py-2 text-sm text-ink shadow-card hover:bg-surface-sunken"
    >
      {theme === "dark" ? "☀️" : "🌙"} <span className="sr-only">{label}</span>
    </button>
  );
}
