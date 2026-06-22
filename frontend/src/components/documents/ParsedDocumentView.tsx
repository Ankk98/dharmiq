import { useEffect, useRef, useState } from "react";

import {
  fetchDocumentChunk,
  fetchDocumentChunks,
  type DocumentChunkListItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type ParsedDocumentViewProps = {
  documentId: string;
  sourceType: "corpus" | "upload";
  chunkId?: string;
  quoteStart?: number;
  quoteEnd?: number;
};

function canHighlight(
  text: string,
  quoteStart?: number,
  quoteEnd?: number,
): quoteStart is number {
  return (
    quoteStart != null &&
    quoteEnd != null &&
    quoteStart >= 0 &&
    quoteEnd > quoteStart &&
    quoteEnd <= text.length
  );
}

function ChunkText({
  text,
  quoteStart,
  quoteEnd,
}: {
  text: string;
  quoteStart?: number;
  quoteEnd?: number;
}) {
  if (!canHighlight(text, quoteStart, quoteEnd)) {
    return <>{text}</>;
  }

  return (
    <>
      {text.slice(0, quoteStart)}
      <mark className="bg-warning/25 text-foreground rounded-sm px-0.5">
        {text.slice(quoteStart, quoteEnd)}
      </mark>
      {text.slice(quoteEnd)}
    </>
  );
}

function ChunkRow({
  chunk,
  isActive,
  fullText,
  quoteStart,
  quoteEnd,
}: {
  chunk: DocumentChunkListItem;
  isActive: boolean;
  fullText?: string;
  quoteStart?: number;
  quoteEnd?: number;
}) {
  const rowRef = useRef<HTMLDivElement>(null);
  const displayText = fullText ?? chunk.preview;
  const meta =
    chunk.page_start != null
      ? `p. ${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ""}`
      : `chunk ${chunk.chunk_index + 1}`;

  useEffect(() => {
    if (isActive) {
      rowRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [isActive, fullText]);

  return (
    <div
      ref={rowRef}
      className={cn(
        "doc-panel-chunk border-border border-b px-3.5 py-2.5",
        isActive && "bg-primary/6",
      )}
    >
      <p className="text-faint mb-1 text-[0.62em] tracking-wide uppercase">
        {chunk.section_label ?? meta}
      </p>
      <p className="font-mono text-[0.72em] leading-relaxed break-words whitespace-pre-wrap">
        <ChunkText text={displayText} quoteStart={quoteStart} quoteEnd={quoteEnd} />
      </p>
    </div>
  );
}

export function ParsedDocumentView({
  documentId,
  sourceType,
  chunkId,
  quoteStart,
  quoteEnd,
}: ParsedDocumentViewProps) {
  const [chunks, setChunks] = useState<DocumentChunkListItem[]>([]);
  const [highlightText, setHighlightText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const shouldHighlight =
    chunkId != null && quoteStart != null && quoteEnd != null;

  useEffect(() => {
    let active = true;

    void (async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetchDocumentChunks(documentId, sourceType);
        if (!active) {
          return;
        }
        setChunks(response.chunks);
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load parsed text");
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [documentId, sourceType]);

  useEffect(() => {
    if (!shouldHighlight || !chunkId) {
      return;
    }

    let active = true;
    void (async () => {
      try {
        const chunk = await fetchDocumentChunk(documentId, chunkId, sourceType);
        if (active) {
          setHighlightText(chunk.text);
        }
      } catch {
        if (active) {
          setHighlightText(null);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [chunkId, documentId, quoteEnd, quoteStart, shouldHighlight, sourceType]);

  if (isLoading) {
    return <p className="text-muted-foreground p-4 text-sm">Loading indexed text…</p>;
  }

  if (error) {
    return <p className="text-destructive p-4 text-sm">{error}</p>;
  }

  if (chunks.length === 0) {
    return (
      <p className="text-muted-foreground p-4 text-sm">
        No indexed text is available for this document yet.
      </p>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {chunks.map((chunk) => {
        const isActive = chunk.chunk_id === chunkId;
        return (
          <ChunkRow
            key={chunk.chunk_id}
            chunk={chunk}
            isActive={isActive}
            fullText={isActive && shouldHighlight ? highlightText ?? undefined : undefined}
            quoteStart={isActive ? quoteStart : undefined}
            quoteEnd={isActive ? quoteEnd : undefined}
          />
        );
      })}
    </div>
  );
}
