import { t } from "../../i18n";

export function taskTypeLabel(value: string): string {
  switch (value) {
    case "review":
      return t("tasks.type.review");
    case "extension":
      return t("tasks.type.extension");
    case "settlement":
      return t("tasks.type.settlement");
    case "guarantee_return":
      return t("tasks.type.guaranteeReturn");
    case "report":
      return t("tasks.type.report");
    case "meeting":
      return t("tasks.type.meeting");
    default:
      return t("tasks.type.other");
  }
}

export function statusLabel(value: string): string {
  switch (value) {
    case "in_progress":
      return t("tasks.status.inProgress");
    case "done":
      return t("tasks.status.done");
    case "cancelled":
      return t("tasks.status.cancelled");
    default:
      return t("tasks.status.pending");
  }
}
