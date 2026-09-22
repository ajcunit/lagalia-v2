import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

import { getAccessToken } from "../auth/session";
import { t } from "../i18n";
import { Skeleton } from "./ui";

/** Visor de PDF intern (specs/pdf-viewer.md): baixa el contingut amb fetch
 *  autenticat i el mostra en un iframe amb object URL — cap descàrrega al
 *  disc de l'usuari i cap token per query string. */
export function PdfViewerModal(props: {
  title: string;
  contentUrl: string;
  onClose: () => void;
}) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;

    async function load() {
      const token = getAccessToken();
      const response = await fetch(props.contentUrl, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        if (!cancelled) setError(t("pdfViewer.loadError"));
        return;
      }
      const blob = await response.blob();
      if (blob.type !== "application/pdf") {
        // No és un PDF: mai s'incrusta; s'ofereix com a descàrrega.
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = props.title;
        link.click();
        URL.revokeObjectURL(url);
        if (!cancelled) props.onClose();
        return;
      }
      const url = URL.createObjectURL(blob);
      revoked = url;
      if (cancelled) {
        URL.revokeObjectURL(url);
        return;
      }
      setObjectUrl(url);
    }

    void load();
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.contentUrl]);

  useEffect(() => {
    closeRef.current?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") props.onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={props.title}
      className="fixed inset-0 z-50 flex flex-col bg-black/60 p-3 sm:p-6"
      onClick={props.onClose}
    >
      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-line bg-surface-raised shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
          <h2 className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
            {props.title}
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={props.onClose}
            aria-label={t("pdfViewer.close")}
            className="rounded-md p-1.5 text-muted hover:bg-surface-sunken hover:text-ink"
          >
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 bg-surface-sunken">
          {error ? (
            <p className="p-6 text-sm text-danger">{error}</p>
          ) : objectUrl ? (
            <iframe src={objectUrl} title={props.title} className="h-full w-full border-0" />
          ) : (
            <div className="p-6">
              <Skeleton rows={8} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
