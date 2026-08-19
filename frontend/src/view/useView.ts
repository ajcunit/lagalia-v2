import { useContext } from "react";

import { ViewContext, type ViewContextValue } from "./context";

/** Vista global de dades (specs/view-selector.md). */
export function useView(): ViewContextValue {
  const context = useContext(ViewContext);
  if (context === undefined) throw new Error("useView requereix ViewProvider");
  return context;
}
