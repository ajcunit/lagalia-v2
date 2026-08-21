/** Formats regionals centralitzats (10-ui.md §2): únic lloc per a ca-ES. */

const currencyFormat = new Intl.NumberFormat("ca-ES", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
});

// dd/mm/yyyy (petició d'usuari 2026-08-21): compacte i sense ambigüitat a
// les taules; el canvi és aquí i val per a tota l'aplicació.
const dateFormat = new Intl.DateTimeFormat("ca-ES", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const dateTimeFormat = new Intl.DateTimeFormat("ca-ES", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
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

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${value} B`;
  const units = ["kB", "MB", "GB"];
  let size = value;
  let unit = "B";
  for (const next of units) {
    if (size < 1024) break;
    size /= 1024;
    unit = next;
  }
  return `${size.toLocaleString("ca-ES", { maximumFractionDigits: 1 })} ${unit}`;
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
