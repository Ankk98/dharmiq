import { createContext } from "react";

export type DocumentPanelParams = {
  documentId: string;
  sourceType: "corpus" | "upload";
  chunkId?: string;
  quote?: string;
  sectionLabel?: string;
};

export type DocumentPanelContextValue = {
  isOpen: boolean;
  params: DocumentPanelParams | null;
  panelWidthPx: number | null;
  isResizing: boolean;
  openDocument: (
    params: DocumentPanelParams,
    options?: { returnTo?: string },
  ) => void;
  closeDocument: () => void;
  setPanelWidthPx: (width: number) => void;
  resetPanelWidth: () => void;
  setIsResizing: (value: boolean) => void;
};

export const DocumentPanelContext = createContext<DocumentPanelContextValue | null>(
  null,
);
