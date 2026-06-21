import {
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { documentViewerPath } from "@/lib/api";
import {
  DocumentPanelContext,
  type DocumentPanelParams,
} from "@/providers/document-panel-context";

function parseDocumentIdFromPath(pathname: string): string | undefined {
  const match = pathname.match(/^\/docs\/([^/]+)$/);
  return match?.[1];
}

function parsePanelParams(
  documentId: string | undefined,
  searchParams: URLSearchParams,
): DocumentPanelParams | null {
  if (!documentId) {
    return null;
  }

  const sourceType = searchParams.get("source_type");
  const resolvedSource: "corpus" | "upload" =
    sourceType === "upload" ? "upload" : "corpus";

  return {
    documentId,
    sourceType: resolvedSource,
    chunkId: searchParams.get("chunk") ?? undefined,
    quote: searchParams.get("quote") ?? undefined,
    sectionLabel: searchParams.get("section") ?? undefined,
  };
}

export function DocumentPanelProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [panelWidthPx, setPanelWidthPxState] = useState<number | null>(null);
  const [isResizing, setIsResizing] = useState(false);

  const documentId = parseDocumentIdFromPath(location.pathname);
  const params = parsePanelParams(documentId, searchParams);
  const isOpen = params !== null;

  const openDocument = useCallback(
    (next: DocumentPanelParams, options?: { returnTo?: string }) => {
      const path = documentViewerPath(next.documentId, next.sourceType, {
        chunkId: next.chunkId,
        quote: next.quote,
        sectionLabel: next.sectionLabel,
      });
      const returnTo =
        options?.returnTo ?? `${location.pathname}${location.search}`;
      setPanelWidthPxState(null);
      navigate(path, { state: { returnTo } });
    },
    [location.pathname, location.search, navigate],
  );

  const closeDocument = useCallback(() => {
    const returnTo =
      (location.state as { returnTo?: string } | null)?.returnTo ?? "/";
    setPanelWidthPxState(null);
    navigate(returnTo);
  }, [location.state, navigate]);

  const setPanelWidthPx = useCallback((width: number) => {
    setPanelWidthPxState(width);
  }, []);

  const resetPanelWidth = useCallback(() => {
    setPanelWidthPxState(null);
  }, []);

  const value = useMemo(
    () => ({
      isOpen,
      params,
      panelWidthPx,
      isResizing,
      openDocument,
      closeDocument,
      setPanelWidthPx,
      resetPanelWidth,
      setIsResizing,
    }),
    [
      isOpen,
      params,
      panelWidthPx,
      isResizing,
      openDocument,
      closeDocument,
      setPanelWidthPx,
      resetPanelWidth,
    ],
  );

  return (
    <DocumentPanelContext.Provider value={value}>
      {children}
    </DocumentPanelContext.Provider>
  );
}
