import { createContext } from "react";

/** Vista global de dades (specs/view-selector.md): "all" (tot l'ens, si el
 *  rol ho permet), "user" (els meus departaments) o "dept:<id>" (un de
 *  concret). El servidor SEMPRE revalida: això només tria què es demana. */
export type ViewValue = string;

export interface ViewContextValue {
  view: ViewValue;
  setView: (view: ViewValue) => void;
}

export const ViewContext = createContext<ViewContextValue | undefined>(undefined);
