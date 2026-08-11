import { Link } from "react-router-dom";

import { t } from "../i18n";

export function NotFound() {
  return (
    <main id="content" className="mx-auto max-w-3xl px-6 py-24 text-center">
      <p className="text-6xl font-bold tabular-nums text-accent">404</p>
      <h1 className="mt-4 text-2xl font-semibold text-ink">{t("notFound.title")}</h1>
      <p className="mt-2 text-muted">{t("notFound.description")}</p>
      <Link
        to="/"
        className="mt-8 inline-block rounded-md bg-accent px-4 py-2 font-medium text-accent-ink shadow-card hover:opacity-90"
      >
        {t("notFound.backHome")}
      </Link>
    </main>
  );
}
