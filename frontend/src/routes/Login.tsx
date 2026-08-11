import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import type { Problem } from "../api/problem";
import { useAuth } from "../auth/AuthProvider";
import { useSetupStatus } from "../auth/useSetupStatus";
import { ProblemAlert } from "../components/ProblemAlert";
import { ThemeToggle } from "../components/ThemeToggle";
import { t } from "../i18n";

export function Login() {
  const { status, login } = useAuth();
  const setup = useSetupStatus();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState<Problem | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (setup.data?.needs_setup) return <Navigate to="/setup" replace />;
  if (status === "authenticated") return <Navigate to="/" replace />;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setProblem(null);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (error) {
      setProblem(error as Problem);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main id="content" className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-6">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <h1 className="text-3xl font-bold tracking-tight text-ink">{t("app.name")}</h1>
      <p className="mt-1 text-muted">{t("app.tagline")}</p>

      <form
        onSubmit={handleSubmit}
        className="mt-8 space-y-4 rounded-lg border border-line bg-surface-raised p-6 shadow-card"
        aria-labelledby="login-title"
      >
        <div>
          <h2 id="login-title" className="text-lg font-semibold text-ink">
            {t("login.title")}
          </h2>
          <p className="text-sm text-muted">{t("login.subtitle")}</p>
        </div>

        <div>
          <label htmlFor="email" className="block text-sm font-medium text-ink">
            {t("login.email")}
          </label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-ink"
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-ink">
            {t("login.password")}
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-ink"
          />
        </div>

        <ProblemAlert problem={problem} />

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-accent px-4 py-2 font-medium text-accent-ink shadow-card hover:opacity-90 disabled:opacity-60"
        >
          {submitting ? t("login.submitting") : t("login.submit")}
        </button>
      </form>
    </main>
  );
}
