import { useCallback, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { XIcon } from "lucide-react";

import { ParsedDocumentView } from "@/components/documents/ParsedDocumentView";
import { useDocumentPanel } from "@/hooks/useDocumentPanel";
import { useDocumentViewer } from "@/hooks/useDocumentViewer";
import {
  CHAT_MIN_WIDTH_PX,
  DOC_PANEL_MIN_WIDTH_PX,
} from "@/lib/design/constants";
import { cn } from "@/lib/utils";

type DocumentPanelTab = "original" | "parsed";

type DocumentPanelProps = {
  sidebarWidthPx: number;
  shellRef: React.RefObject<HTMLElement | null>;
};

export function DocumentPanel({ sidebarWidthPx, shellRef }: DocumentPanelProps) {
  const {
    isOpen,
    params,
    closeDocument,
    resetPanelWidth,
    isResizing,
    setIsResizing,
    setPanelWidthPx,
  } = useDocumentPanel();
  const resizerRef = useRef<HTMLDivElement>(null);

  const documentId = params?.documentId ?? "";
  const sourceType = params?.sourceType ?? "corpus";
  const [tabState, setTabState] = useState<{ docId: string; tab: DocumentPanelTab }>({
    docId: "",
    tab: "original",
  });
  const activeTab = tabState.docId === documentId ? tabState.tab : "original";
  const setActiveTab = useCallback(
    (tab: DocumentPanelTab) => {
      setTabState({ docId: documentId, tab });
    },
    [documentId],
  );
  const { title, objectUrl, error, isLoading } = useDocumentViewer({
    documentId,
    sourceType,
  });

  const subtitle =
    params?.sectionLabel ??
    (params?.chunkId ? `Chunk ${params.chunkId.slice(0, 8)}…` : null) ??
    (sourceType === "upload" ? "Your upload" : "Statutory source");

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsResizing(true);
      resizerRef.current?.classList.add("doc-panel-resizer--drag");

      const onMove = (moveEvent: PointerEvent) => {
        const shell = shellRef.current;
        if (!shell) {
          return;
        }
        const rect = shell.getBoundingClientRect();
        const avail = rect.width - sidebarWidthPx;
        let width = rect.right - moveEvent.clientX;
        width = Math.max(
          DOC_PANEL_MIN_WIDTH_PX,
          Math.min(width, avail - CHAT_MIN_WIDTH_PX),
        );
        setPanelWidthPx(width);
      };

      const onUp = () => {
        setIsResizing(false);
        resizerRef.current?.classList.remove("doc-panel-resizer--drag");
        document.removeEventListener("pointermove", onMove);
        document.removeEventListener("pointerup", onUp);
      };

      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    },
    [setIsResizing, setPanelWidthPx, shellRef, sidebarWidthPx],
  );

  const handleResizerDoubleClick = useCallback(() => {
    resetPanelWidth();
  }, [resetPanelWidth]);

  return (
    <>
      {isOpen ? (
        <button
          type="button"
          aria-label="Close document viewer"
          className="fixed inset-0 z-30 bg-black/20 md:hidden"
          onClick={closeDocument}
        />
      ) : null}

      <aside
        aria-hidden={!isOpen}
        className={cn(
          "doc-panel border-border bg-card relative flex min-w-0 flex-col overflow-hidden border-l",
          "max-md:fixed max-md:inset-0 max-md:z-40 max-md:border-l-0 max-md:transition-transform max-md:duration-[380ms] max-md:ease-[var(--ease-default)]",
          isOpen
            ? "max-md:translate-x-0"
            : "max-md:pointer-events-none max-md:translate-x-full max-md:opacity-0",
          !isOpen && "pointer-events-none opacity-0 max-md:opacity-0",
        )}
      >
        <div
          ref={resizerRef}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize document panel"
          title="Drag to resize · double-click to reset"
          className={cn(
            "doc-panel-resizer absolute top-0 bottom-0 left-[-5px] z-[25] hidden w-[11px] cursor-col-resize items-center justify-center md:flex",
            isResizing && "doc-panel-resizer--drag",
          )}
          onPointerDown={handlePointerDown}
          onDoubleClick={handleResizerDoubleClick}
        />

        <header className="border-border flex shrink-0 items-center gap-2.5 border-b px-3.5 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[0.8em] font-semibold">{title}</p>
            <p className="text-faint truncate text-[0.66em] font-normal">{subtitle}</p>
          </div>
          <button
            type="button"
            aria-label="Close document panel"
            className="text-muted-foreground border-border hover:text-foreground ml-auto grid size-[26px] shrink-0 place-items-center rounded-[7px] border transition-colors"
            onClick={closeDocument}
          >
            <XIcon className="size-3.5" strokeWidth={1.8} />
          </button>
        </header>

        <div
          className="border-border flex shrink-0 gap-1 border-b px-3.5 py-2"
          role="tablist"
          aria-label="Document view"
        >
          {(["original", "parsed"] as const).map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              className={cn(
                "rounded-[7px] px-2.5 py-1 text-[0.72em] capitalize transition-colors",
                activeTab === tab
                  ? "bg-primary/10 text-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground",
              )}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          {activeTab === "original" ? (
            <>
              {isOpen && error ? (
                <p className="text-destructive p-4 text-sm">{error}</p>
              ) : null}
              {isOpen && !error && isLoading ? (
                <p className="text-muted-foreground p-4 text-sm">Loading document…</p>
              ) : null}
              {isOpen && objectUrl ? (
                <iframe
                  title={title}
                  src={objectUrl}
                  className="absolute inset-0 h-full w-full border-0"
                />
              ) : null}
            </>
          ) : (
            isOpen ? (
              <ParsedDocumentView
                documentId={documentId}
                sourceType={sourceType}
                chunkId={params?.chunkId}
                quoteStart={params?.quoteStart}
                quoteEnd={params?.quoteEnd}
              />
            ) : null
          )}
        </div>

        <footer className="border-border text-faint shrink-0 border-t px-3.5 py-2.5 text-[0.7em]">
          {activeTab === "parsed"
            ? "Indexed text used for retrieval — layout may differ from the original PDF."
            : "PDF preview of the cited source document."}
        </footer>
      </aside>
    </>
  );
}
