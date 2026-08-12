/** Formats regionals centralitzats (10-ui.md §2): únic lloc per a ca-ES. */

const currencyFormat = new Intl.NumberFormat("ca-ES", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
});

const dateFormat = new Intl.DateTimeFormat("ca-ES", { dateStyle: "medium" });

const dateTimeFormat = new Intl.DateTimeFormat("ca-ES", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatCurrency(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) return "—";
  return currencyFormat.format(amount);
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return dateFormat.format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return dateTimeFormat.format(date);
}

export function formatDuration(months: number | null | undefined): string {
  if (!months) return "—";
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const parts: string[] = [];
  if (years) parts.push(years === 1 ? "1 any" : `${years} anys`);
  if (rest) parts.push(rest === 1 ? "1 mes" : `${rest} mesos`);
  return parts.join(" i ") || "—";
}
