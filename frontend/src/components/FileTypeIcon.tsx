import type { LucideIcon } from "lucide-react";
import {
  File,
  FileArchive,
  FileImage,
  FileSpreadsheet,
  FileText,
} from "lucide-react";

const BY_EXTENSION: Record<string, { icon: LucideIcon; tone: string }> = {
  pdf: { icon: FileText, tone: "text-red-500" },
  doc: { icon: FileText, tone: "text-blue-500" },
  docx: { icon: FileText, tone: "text-blue-500" },
  odt: { icon: FileText, tone: "text-blue-500" },
  rtf: { icon: FileText, tone: "text-blue-500" },
  xls: { icon: FileSpreadsheet, tone: "text-green-600" },
  xlsx: { icon: FileSpreadsheet, tone: "text-green-600" },
  ods: { icon: FileSpreadsheet, tone: "text-green-600" },
  csv: { icon: FileSpreadsheet, tone: "text-green-600" },
  zip: { icon: FileArchive, tone: "text-amber-500" },
  rar: { icon: FileArchive, tone: "text-amber-500" },
  "7z": { icon: FileArchive, tone: "text-amber-500" },
  jpg: { icon: FileImage, tone: "text-purple-500" },
  jpeg: { icon: FileImage, tone: "text-purple-500" },
  png: { icon: FileImage, tone: "text-purple-500" },
  gif: { icon: FileImage, tone: "text-purple-500" },
};

/** Icona pel tipus de fitxer, inferit de l'extensió del nom. */
export function FileTypeIcon(props: { name: string | null | undefined; className?: string }) {
  const match = /\.([a-z0-9]{1,5})\s*$/i.exec(props.name ?? "");
  const entry = match ? BY_EXTENSION[match[1]!.toLowerCase()] : undefined;
  const Icon = entry?.icon ?? File;
  return (
    <Icon
      aria-hidden
      className={`${props.className ?? "h-4 w-4"} shrink-0 ${entry?.tone ?? "text-muted"}`}
    />
  );
}
