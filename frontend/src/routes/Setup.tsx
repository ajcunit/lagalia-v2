import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { api } from "../api/client";
import { asProblem, type Problem } from "../api/problem";
import { passwordChecklist, passwordSatisfies } from "../auth/passwordChecklist";
import { useSetupStatus } from "../auth/useSetupStatus";
import { ProblemAlert } from "../components/ProblemAlert";
import { ThemeToggle } from "../components/ThemeToggle";
import { t } from "../i18n";

const TOTAL_STEPS = 4;

interface WizardData {
  name: string;
  email: string;
  password: string;
  organization_name: string;
  ine10_code: string;
}

const EMPTY: WizardData = {
  name: "",
  email: "",
  password: "",
  organization_name: "",
  ine10_code: "",
};

function Field(props: {
  id: keyof WizardData;
  label: string;
  type?: string;
  hint?: string;
  required?: boolean;
  autoComplete?: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label htmlFor={props.id} className="block text-sm font-medium text-ink">
        {props.label}
      </label>
      <input
        id={props.id}
        type={props.type ?? "text"}
        required={props.required}
        autoComplete={props.autoComplete}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        aria-describedby={props.hint ? `${props.id}-hint` : undefined}
        className="mt-1 w-full rounded-md border border-line bg-surface px-3 py-2 text-ink"
      />
      {props.hint && (
        <p id={`${props.id}-hint`} className="mt-1 text-xs text-muted">
          {props.hint}
        </p>
      )}
    </div>
  );
}

function PasswordChecklist({ password }: { password: string }) {
  return (
    <div aria-live="polite">
      <p className="text-sm font-medium text-ink">{t("setup.password.requirements")}</p>
      <ul className="mt-1 space-y-1 text-sm">
        {passwordChecklist(password).map((item) => (
          <li key={item.labelKey} className={item.ok ? "text-success" : "text-muted"}>
            <span aria-hidden="true">{item.ok ? "✓" : "○"}</span> {t(item.labelKey)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Setup() {
  const setup = useSetupStatus();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [data, setData] = useState<WizardData>(EMPTY);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  if (setup.data && !setup.data.needs_setup && !done) {
    return <Navigate to="/login" replace />;
  }

  const set = (field: keyof WizardData) => (value: string) =>
    setData((current) => ({ ...current, [field]: value }));

  function next(event: FormEvent) {
    event.preventDefault();
    setStep((current) => Math.min(current + 1, TOTAL_STEPS));
  }

  async function submit() {
    setSubmitting(true);
    setProblem(null);
    const { error, response } = await api.POST("/setup/initialize", {
      body: {
        name: data.name,
        email: data.email,
        password: data.password,
        ...(data.organization_name && { organization_name: data.organization_name }),
        ...(data.ine10_code && { ine10_code: data.ine10_code }),
      },
    });
    setSubmitting(false);
    if (error !== undefined) {
      setProblem(asProblem(error, response));
      return;
    }
    // El sistema acaba de deixar d'estar pendent: sense això, el login
    // rebotaria cap al wizard fins que caduqués la cache.
    queryClient.setQueryData(["setup-status"], { needs_setup: false });
    setDone(true);
  }

  return (
    <main id="content" className="mx-auto max-w-lg px-6 py-16">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <h1 className="text-2xl font-bold tracking-tight text-ink">{t("setup.title")}</h1>
      {!done && (
        <p className="mt-1 text-sm text-muted">
          {t("setup.step", { current: step, total: TOTAL_STEPS })}
        </p>
      )}

      <div className="mt-6 rounded-lg border border-line bg-surface-raised p-6 shadow-card">
        {done ? (
          <section aria-labelledby="done-title">
            <h2 id="done-title" className="text-lg font-semibold text-success">
              {t("setup.done.title")}
            </h2>
            <p className="mt-2 text-muted">{t("setup.done.body")}</p>
            <Link
              to="/login"
              className="mt-6 inline-block rounded-md bg-accent px-4 py-2 font-medium text-accent-ink shadow-card hover:opacity-90"
            >
              {t("setup.done.goLogin")}
            </Link>
          </section>
        ) : step === 1 ? (
          <section aria-labelledby="step1-title">
            <h2 id="step1-title" className="text-lg font-semibold text-ink">
              {t("setup.welcome.title")}
            </h2>
            <p className="mt-2 text-muted">{t("setup.welcome.body")}</p>
            <button
              type="button"
              onClick={() => setStep(2)}
              className="mt-6 rounded-md bg-accent px-4 py-2 font-medium text-accent-ink shadow-card hover:opacity-90"
            >
              {t("setup.welcome.start")}
            </button>
          </section>
        ) : step === 2 ? (
          <form onSubmit={next} aria-labelledby="step2-title" className="space-y-4">
            <h2 id="step2-title" className="text-lg font-semibold text-ink">
              {t("setup.admin.title")}
            </h2>
            <Field
              id="name"
              label={t("setup.admin.name")}
              required
              autoComplete="name"
              value={data.name}
              onChange={set("name")}
            />
            <Field
              id="email"
              label={t("setup.admin.email")}
              type="email"
              required
              autoComplete="username"
              value={data.email}
              onChange={set("email")}
            />
            <Field
              id="password"
              label={t("setup.admin.password")}
              type="password"
              required
              autoComplete="new-password"
              value={data.password}
              onChange={set("password")}
            />
            <PasswordChecklist password={data.password} />
            <div className="flex justify-between">
              <button type="button" onClick={() => setStep(1)} className="text-muted">
                {t("common.back")}
              </button>
              <button
                type="submit"
                disabled={!passwordSatisfies(data.password)}
                className="rounded-md bg-accent px-4 py-2 font-medium text-accent-ink shadow-card hover:opacity-90 disabled:opacity-60"
              >
                {t("common.next")}
              </button>
            </div>
          </form>
        ) : step === 3 ? (
          <form onSubmit={next} aria-labelledby="step3-title" className="space-y-4">
            <h2 id="step3-title" className="text-lg font-semibold text-ink">
              {t("setup.org.title")}
            </h2>
            <Field
              id="organization_name"
              label={t("setup.org.name")}
              value={data.organization_name}
              onChange={set("organization_name")}
            />
            <Field
              id="ine10_code"
              label={t("setup.org.ine10")}
              hint={t("setup.org.ine10Hint")}
              value={data.ine10_code}
              onChange={set("ine10_code")}
            />
            <div className="flex justify-between">
              <button type="button" onClick={() => setStep(2)} className="text-muted">
                {t("common.back")}
              </button>
              <button
                type="submit"
                className="rounded-md bg-accent px-4 py-2 font-medium text-accent-ink shadow-card hover:opacity-90"
              >
                {t("common.next")}
              </button>
            </div>
          </form>
        ) : (
          <section aria-labelledby="step4-title" className="space-y-4">
            <h2 id="step4-title" className="text-lg font-semibold text-ink">
              {t("setup.confirm.title")}
            </h2>
            <p className="text-muted">{t("setup.confirm.body")}</p>
            <dl className="space-y-1 text-sm">
              <div className="flex gap-2">
                <dt className="font-medium text-ink">{t("setup.admin.name")}:</dt>
                <dd className="text-muted">{data.name}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-medium text-ink">{t("setup.admin.email")}:</dt>
                <dd className="text-muted">{data.email}</dd>
              </div>
              {data.organization_name && (
                <div className="flex gap-2">
                  <dt className="font-medium text-ink">{t("setup.org.name")}:</dt>
                  <dd className="text-muted">{data.organization_name}</dd>
                </div>
              )}
              {data.ine10_code && (
                <div className="flex gap-2">
                  <dt className="font-medium text-ink">{t("setup.org.ine10")}:</dt>
                  <dd className="text-muted tabular-nums">{data.ine10_code}</dd>
                </div>
              )}
            </dl>
            <ProblemAlert problem={problem} />
            <div className="flex justify-between">
              <button type="button" onClick={() => setStep(3)} className="text-muted">
                {t("common.back")}
              </button>
              <button
                type="button"
                onClick={() => void submit()}
                disabled={submitting}
                className="rounded-md bg-accent px-4 py-2 font-medium text-accent-ink shadow-card hover:opacity-90 disabled:opacity-60"
              >
                {submitting ? t("setup.confirm.submitting") : t("setup.confirm.submit")}
              </button>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
