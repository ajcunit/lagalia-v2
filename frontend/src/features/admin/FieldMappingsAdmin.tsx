import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { ArrowLeftRight } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";

type Mapping = components["schemas"]["FieldMapping"];

const SOURCES = [
  { key: "socrata", labelKey: "mapping.sourceSocrata" },
  { key: "rpc", labelKey: "mapping.sourceRpc" },
  { key: "execution", labelKey: "mapping.sourceExecution" },
  { key: "pscp", labelKey: "mapping.sourcePscp" },
] as const;

const PSCP_PHASES = ["licitacio", "avaluacio", "adjudicacio", "formalitzacio", "previ"] as const;

/** Mapejador de camps font → model (specs/field-mapping.md). */
export function FieldMappingsAdmin() {
  const queryClient = useQueryClient();
  const [source, setSource] = useState<string>("socrata");
  const [fileCode, setFileCode] = useState("");
  const [phase, setPhase] = useState<string>("licitacio");
  const [sampleKey, setSampleKey] = useState<{ code: string; phase: string | null } | null>(null);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  function switchSource(next: string) {
    setSource(next);
    setSampleKey(null);
    setEdits({});
    setMessage(null);
  }

  const mappings = useQuery({
    queryKey: ["field-mappings", source],
    queryFn: async () => {
      const { data, error } = await api.GET("/field-mappings/{source}", {
        params: { path: { source } },
      });
      if (error !== undefined) throw error;
      return data.data;
    },
  });

  const sample = useQuery({
    queryKey: ["field-mapping-sample", source, sampleKey],
    enabled: sampleKey !== null,
    retry: false,
    queryFn: async () => {
      const { data, error } = await api.GET("/field-mappings/{source}/sample", {
        params: {
          path: { source },
          query: {
            file_code: sampleKey!.code,
            ...(source === "pscp" && sampleKey!.phase ? { phase: sampleKey!.phase } : {}),
          },
        },
      });
      if (error !== undefined) throw error;
      return data;
    },
  });
  const sampleFields = (sample.data?.fields ?? {}) as Record<string, unknown>;
  const sampleKeys = Object.keys(sampleFields).sort();

  const save = useMutation({
    mutationFn: async (input: { target: string; sourceField: string }) => {
      const { error } = await api.PUT("/field-mappings/{source}/{target_field}", {
        params: { path: { source, target_field: input.target } },
        body: { source_field: input.sourceField },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: (_data, input) => {
      setEdits((prev) =>
        Object.fromEntries(Object.entries(prev).filter(([key]) => key !== input.target)),
      );
      setMessage(t("mapping.saved", { field: input.target }));
      void queryClient.invalidateQueries({ queryKey: ["field-mappings", source] });
    },
    onError: () => setMessage(t("mapping.saveError")),
  });

  const reset = useMutation({
    mutationFn: async (target: string) => {
      const { error } = await api.DELETE("/field-mappings/{source}/{target_field}", {
        params: { path: { source, target_field: target } },
      });
      if (error !== undefined) throw error;
    },
    onSuccess: (_data, target) => {
      setEdits((prev) =>
        Object.fromEntries(Object.entries(prev).filter(([key]) => key !== target)),
      );
      setMessage(t("mapping.resetDone", { field: target }));
      void queryClient.invalidateQueries({ queryKey: ["field-mappings", source] });
    },
  });

  const remap = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/field-mappings/{source}/actions/remap", {
        params: { path: { source } },
      });
      if (error !== undefined) throw error;
      return data;
    },
    onSuccess: () => setMessage(t("mapping.remapQueued")),
    onError: () => setMessage(t("mapping.remapError")),
  });

  function sampleValue(sourceField: string): string {
    if (sampleKey === null || sample.data === undefined) return "";
    const value = sampleFields[sourceField.startsWith("~") ? "" : sourceField];
    if (value === undefined) return t("mapping.sampleMissing");
    if (typeof value === "object") return JSON.stringify(value).slice(0, 60);
    return String(value).slice(0, 60);
  }

  function loadSample() {
    const code = fileCode.trim();
    if (code) setSampleKey({ code, phase: source === "pscp" ? phase : null });
  }

  return (
    <div>
      <PageHeader
        icon={ArrowLeftRight}
        title={t("mapping.title")}
        subtitle={t("mapping.intro")}
        backTo="/admin"
        actions={
          <Button
            tone="accent"
            disabled={remap.isPending}
            onClick={() => {
              if (window.confirm(t(source === "pscp" ? "mapping.remapConfirmPscp" : "mapping.remapConfirm")))
                remap.mutate();
            }}
          >
            {remap.isPending ? t("mapping.remapping") : t("mapping.remap")}
          </Button>
        }
      />

      <div className="mt-4 flex flex-wrap items-center gap-1.5" role="tablist">
        {SOURCES.map((entry) => (
          <button
            key={entry.key}
            type="button"
            role="tab"
            aria-selected={source === entry.key}
            onClick={() => switchSource(entry.key)}
            className={`rounded-full border px-3 py-1 text-sm ${
              source === entry.key
                ? "border-accent bg-accent-soft text-ink"
                : "border-line text-muted hover:text-ink"
            }`}
          >
            {t(entry.labelKey as Parameters<typeof t>[0])}
          </button>
        ))}
      </div>

      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          loadSample();
        }}
      >
        <label className="text-sm text-ink">
          {t("mapping.sampleLabel")}
          <input
            value={fileCode}
            onChange={(e) => setFileCode(e.target.value)}
            placeholder="2885/2026"
            className="mt-1 block w-56 rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
          />
        </label>
        {source === "pscp" && (
          <label className="text-sm text-ink">
            {t("mapping.phaseLabel")}
            <select
              value={phase}
              onChange={(e) => setPhase(e.target.value)}
              className="mt-1 block rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
            >
              {PSCP_PHASES.map((option) => (
                <option key={option} value={option}>
                  {t(`search.phase.${option}` as Parameters<typeof t>[0])}
                </option>
              ))}
            </select>
          </label>
        )}
        <Button onClick={loadSample}>{t("mapping.sampleLoad")}</Button>
        {sample.isError && (
          <span className="text-sm text-danger">{t("mapping.sampleNotFound")}</span>
        )}
        {sample.data !== undefined && (
          <span className="text-sm text-muted">
            {t("mapping.sampleLoaded", {
              code: sample.data.file_code,
              count: String(sampleKeys.length),
            })}
          </span>
        )}
      </form>
      {message && (
        <p aria-live="polite" className="mt-2 text-sm text-muted">
          {message}
        </p>
      )}

      <datalist id="source-field-options">
        {sampleKeys.map((key) => (
          <option key={key} value={key} />
        ))}
      </datalist>

      <div className="mt-4">
        {mappings.isPending ? (
          <Skeleton rows={10} />
        ) : mappings.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface-raised shadow-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th scope="col" className="px-3 py-2 font-medium">{t("mapping.colTarget")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("mapping.colSource")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("mapping.colSample")}</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    {t("mapping.colActions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {mappings.data.map((mapping: Mapping) => {
                  const edited = edits[mapping.target_field];
                  const current = edited ?? mapping.source_field;
                  const dirty = edited !== undefined && edited !== mapping.source_field;
                  return (
                    <tr key={mapping.target_field} className="border-t border-line align-top">
                      <td className="px-3 py-2">
                        <span className="text-ink">{mapping.label}</span>
                        <span className="mt-0.5 block font-mono text-xs text-muted">
                          {mapping.target_field} · {mapping.kind}
                          {mapping.phases && mapping.phases.length > 0 && (
                            <> · {mapping.phases.join(", ")}</>
                          )}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={current}
                          list="source-field-options"
                          aria-label={`${t("mapping.colSource")} — ${mapping.label}`}
                          onChange={(e) =>
                            setEdits({ ...edits, [mapping.target_field]: e.target.value })
                          }
                          className="w-72 rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs"
                        />
                        {mapping.overridden && (
                          <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                            <Badge tone="accent">{t("mapping.overridden")}</Badge>
                            {t("mapping.default")}: <code>{mapping.default_source_field}</code>
                          </span>
                        )}
                      </td>
                      <td className="max-w-64 px-3 py-2 text-xs text-muted">
                        {sampleValue(current)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className="flex justify-end gap-2">
                          <Button
                            disabled={!dirty || save.isPending || !current.trim()}
                            onClick={() =>
                              save.mutate({
                                target: mapping.target_field,
                                sourceField: current.trim(),
                              })
                            }
                          >
                            {t("admin.save")}
                          </Button>
                          {mapping.overridden && (
                            <button
                              type="button"
                              className="text-xs text-accent underline"
                              disabled={reset.isPending}
                              onClick={() => reset.mutate(mapping.target_field)}
                            >
                              {t("mapping.reset")}
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="mt-3 text-xs text-muted">
        {t("mapping.note")}{" "}
        <Link to="/admin/sync" className="text-accent underline">
          {t("mapping.syncLink")}
        </Link>
      </p>
    </div>
  );
}
