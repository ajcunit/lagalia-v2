import { useState } from "react";

import { Badge, Button, EmptyState, Skeleton } from "../../components/ui";
import { Webhook as WebhookIcon } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { formatDateTime } from "../../lib/format";
import {
  useCreateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useUpdateWebhook,
  useWebhookDeliveries,
  useWebhooks,
  type Webhook,
} from "./queries";

const EVENT_CATALOG: Array<{ value: string; labelKey: Parameters<typeof t>[0] }> = [
  { value: "*", labelKey: "webhooks.event.all" },
  { value: "contract.finished", labelKey: "webhooks.event.contractFinished" },
  { value: "contractor.merged", labelKey: "webhooks.event.contractorMerged" },
  { value: "sync.completed", labelKey: "webhooks.event.syncCompleted" },
  { value: "sync.failed", labelKey: "webhooks.event.syncFailed" },
  { value: "task.completed", labelKey: "webhooks.event.taskCompleted" },
];

function eventLabel(value: string): string {
  const entry = EVENT_CATALOG.find((e) => e.value === value);
  return entry ? t(entry.labelKey) : value;
}

function statusBadge(status: string) {
  if (status === "delivered") return <Badge tone="accent">{t("webhooks.delivered")}</Badge>;
  if (status === "failed") return <Badge tone="danger">{t("webhooks.failed")}</Badge>;
  return <Badge tone="neutral">{t("webhooks.pending")}</Badge>;
}

function Deliveries(props: { webhookId: number }) {
  const deliveries = useWebhookDeliveries(props.webhookId);
  if (deliveries.isPending) return <Skeleton rows={3} />;
  if (deliveries.isError || !deliveries.data?.data.length) {
    return <p className="py-2 text-sm text-muted">{t("webhooks.noDeliveries")}</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-muted">
          <th scope="col" className="py-1 pr-2 font-medium">{t("webhooks.col.event")}</th>
          <th scope="col" className="py-1 pr-2 font-medium">{t("webhooks.col.status")}</th>
          <th scope="col" className="py-1 pr-2 font-medium">{t("webhooks.col.attempts")}</th>
          <th scope="col" className="py-1 pr-2 font-medium">{t("webhooks.col.when")}</th>
          <th scope="col" className="py-1 font-medium">{t("webhooks.col.error")}</th>
        </tr>
      </thead>
      <tbody>
        {deliveries.data.data.map((delivery) => (
          <tr key={delivery.id} className="border-t border-line">
            <td className="py-1.5 pr-2 font-mono text-xs">{delivery.event_type}</td>
            <td className="py-1.5 pr-2">{statusBadge(delivery.status)}</td>
            <td className="py-1.5 pr-2 tabular-nums">{delivery.attempts}</td>
            <td className="py-1.5 pr-2 whitespace-nowrap text-muted">
              {formatDateTime(delivery.created_at)}
            </td>
            <td className="max-w-64 truncate py-1.5 text-muted" title={delivery.last_error ?? ""}>
              {delivery.last_error ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function WebhooksAdmin() {
  const webhooks = useWebhooks();
  const create = useCreateWebhook();
  const update = useUpdateWebhook();
  const remove = useDeleteWebhook();
  const test = useTestWebhook();

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>(["*"]);
  const [formError, setFormError] = useState<string | null>(null);
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [testedId, setTestedId] = useState<number | null>(null);

  function toggleEvent(value: string) {
    setEvents((current) => {
      if (value === "*") return ["*"];
      const without = current.filter((e) => e !== "*" && e !== value);
      return current.includes(value) ? without : [...without, value];
    });
  }

  function save() {
    setFormError(null);
    create.mutate(
      { name, url, events },
      {
        onSuccess: (created) => {
          setCreating(false);
          setName("");
          setUrl("");
          setEvents(["*"]);
          setNewSecret(created.secret);
          void navigator.clipboard.writeText(created.secret).catch(() => undefined);
        },
        onError: (error) => {
          const problem = error as { detail?: string; title?: string };
          setFormError(problem.detail ?? problem.title ?? String(error));
        },
      },
    );
  }

  function onTest(webhook: Webhook) {
    test.mutate(webhook.id, {
      onSuccess: () => {
        setTestedId(webhook.id);
        setExpanded(webhook.id);
      },
      onError: (error) =>
        window.alert(t("contract.action.error", { message: String(error) })),
    });
  }

  function onDelete(webhook: Webhook) {
    if (!window.confirm(t("webhooks.confirmDelete", { name: webhook.name }))) return;
    remove.mutate(webhook.id, {
      onError: (error) =>
        window.alert(t("contract.action.error", { message: String(error) })),
    });
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <PageHeader
          backTo="/admin"
          icon={WebhookIcon} title={t("webhooks.title")} subtitle={t("webhooks.intro")} />
        </div>
        {!creating && (
          <Button tone="accent" onClick={() => { setCreating(true); setNewSecret(null); }}>
            {t("webhooks.new")}
          </Button>
        )}
      </div>

      {newSecret && (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-warning/50 bg-warning/10 p-4"
        >
          <p className="font-medium text-ink">{t("webhooks.secretTitle")}</p>
          <p className="mt-1 text-sm text-muted">{t("webhooks.secretNote")}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="rounded bg-surface-sunken px-2 py-1 font-mono text-sm">
              {newSecret}
            </code>
            <Button
              onClick={() => void navigator.clipboard.writeText(newSecret).catch(() => undefined)}
            >
              {t("webhooks.copy")}
            </Button>
            <Button onClick={() => setNewSecret(null)}>{t("webhooks.secretDone")}</Button>
          </div>
        </div>
      )}

      {creating && (
        <div className="mt-4 rounded-lg border border-accent/40 bg-surface-raised p-4 shadow-card">
          <h2 className="text-lg font-semibold text-ink">{t("webhooks.new")}</h2>
          {formError && (
            <p role="alert" className="mt-2 rounded-md bg-danger/10 p-2 text-sm text-ink">
              {formError}
            </p>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-sm text-ink">
              {t("webhooks.field.name")}
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="n8n — notificacions Teams"
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              />
            </label>
            <label className="text-sm text-ink">
              {t("webhooks.field.url")}
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://n8n.cunit.cat/webhook/…"
                className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm font-mono"
              />
            </label>
            <fieldset className="text-sm text-ink sm:col-span-2">
              <legend>{t("webhooks.field.events")}</legend>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                {EVENT_CATALOG.map((event) => (
                  <label key={event.value} className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={events.includes(event.value)}
                      onChange={() => toggleEvent(event.value)}
                    />
                    {t(event.labelKey)}
                    <code className="text-xs text-muted">{event.value}</code>
                  </label>
                ))}
              </div>
            </fieldset>
          </div>
          <div className="mt-4 flex gap-2">
            <Button
              tone="accent"
              disabled={create.isPending || !name || !url || events.length === 0}
              onClick={save}
            >
              {t("admin.save")}
            </Button>
            <Button onClick={() => setCreating(false)}>{t("admin.cancel")}</Button>
          </div>
        </div>
      )}

      <div className="mt-4 space-y-3">
        {webhooks.isPending ? (
          <Skeleton rows={6} />
        ) : webhooks.isError ? (
          <EmptyState icon="⚠️" title={t("admin.loadError")} />
        ) : webhooks.data.data.length === 0 ? (
          <EmptyState icon="🔗" title={t("webhooks.empty")} detail={t("webhooks.emptyDetail")} />
        ) : (
          webhooks.data.data.map((webhook) => (
            <div
              key={webhook.id}
              className="rounded-lg border border-line bg-surface-raised p-4 shadow-card"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-ink">
                    {webhook.name}{" "}
                    {webhook.active ? (
                      <Badge tone="accent">{t("webhooks.active")}</Badge>
                    ) : (
                      <Badge tone="danger">{t("webhooks.inactive")}</Badge>
                    )}
                  </p>
                  <p className="truncate font-mono text-sm text-muted" title={webhook.url}>
                    {webhook.url}
                  </p>
                  <p className="mt-1 flex flex-wrap gap-1">
                    {webhook.events.map((event) => (
                      <span
                        key={event}
                        className="rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-muted"
                      >
                        {eventLabel(event)}
                      </span>
                    ))}
                  </p>
                </div>
                <span className="flex shrink-0 flex-wrap gap-2">
                  <Button disabled={test.isPending} onClick={() => onTest(webhook)}>
                    {t("webhooks.test")}
                  </Button>
                  <Button
                    disabled={update.isPending}
                    onClick={() =>
                      update.mutate({ id: webhook.id, body: { active: !webhook.active } })
                    }
                  >
                    {webhook.active ? t("webhooks.deactivate") : t("webhooks.activate")}
                  </Button>
                  <Button
                    onClick={() => setExpanded(expanded === webhook.id ? null : webhook.id)}
                  >
                    {t("webhooks.deliveries")}
                  </Button>
                  <Button tone="danger" onClick={() => onDelete(webhook)}>
                    {t("webhooks.delete")}
                  </Button>
                </span>
              </div>
              {testedId === webhook.id && (
                <p className="mt-2 rounded-md bg-accent-soft p-2 text-sm text-ink">
                  {t("webhooks.testQueued")}
                </p>
              )}
              {expanded === webhook.id && (
                <div className="mt-3 border-t border-line pt-2">
                  <Deliveries webhookId={webhook.id} />
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
