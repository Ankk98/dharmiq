import { useContext } from "react";

import { DocumentPanelContext } from "@/providers/document-panel-context";

export function useDocumentPanel() {
  const context = useContext(DocumentPanelContext);
  if (!context) {
    throw new Error("useDocumentPanel must be used within DocumentPanelProvider");
  }
  return context;
}
