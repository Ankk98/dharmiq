import type { Citation } from "@/lib/api";
import { documentViewerPath } from "@/lib/api";

const INLINE_CITATION_RE = /\[doc:([^|\]]+)\|chunk:([^\]]+)\]/g;
const NUMERIC_CITATION_RE = /\[(\d+)\]/g;

function citationByMarker(citations: Citation[]): Map<number, Citation> {
  const map = new Map<number, Citation>();
  for (const citation of citations) {
    if (citation.marker != null) {
      map.set(citation.marker, citation);
    }
  }
  return map;
}

export function linkifyNumericCitations(
  text: string,
  citations: Citation[] = [],
): string {
  const byMarker = citationByMarker(citations);
  return text.replace(NUMERIC_CITATION_RE, (match, markerStr: string) => {
    const marker = Number(markerStr);
    const citation = byMarker.get(marker);
    if (!citation) {
      return match;
    }
    return `[${marker}](${documentViewerPath(citation.document_id, citation.source_type)})`;
  });
}

export function linkifyInlineCitations(
  text: string,
  citations: Citation[] = [],
): string {
  const sourceByDoc = new Map(citations.map((item) => [item.document_id, item.source_type]));

  return text.replace(INLINE_CITATION_RE, (_match, docId: string, chunkId: string) => {
    const sourceType = sourceByDoc.get(docId) ?? "corpus";
    const label = chunkId.slice(0, 8);
    return `[${label}](${documentViewerPath(docId, sourceType)})`;
  });
}

function groupCitations(citations: Citation[]): {
  corpus: Citation[];
  upload: Citation[];
} {
  const corpus: Citation[] = [];
  const upload: Citation[] = [];
  const seen = new Set<string>();

  for (const citation of citations) {
    const key = `${citation.source_type}:${citation.document_id}:${citation.marker ?? ""}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    if (citation.source_type === "upload") {
      upload.push(citation);
    } else {
      corpus.push(citation);
    }
  }

  return { corpus, upload };
}

function formatCitationLine(citation: Citation): string {
  const pages =
    citation.page_start != null
      ? ` (pp. ${citation.page_start}${citation.page_end ? `–${citation.page_end}` : ""})`
      : "";
  const label = citation.section_label
    ? `${citation.document_title} — ${citation.section_label}`
    : citation.document_title;
  const marker = citation.marker != null ? `[${citation.marker}] ` : "";
  return `- ${marker}[${label}${pages}](${documentViewerPath(citation.document_id, citation.source_type)})`;
}

export function appendSourcesSection(text: string, citations: Citation[]): string {
  if (citations.length === 0) {
    return text;
  }

  const { corpus, upload } = groupCitations(citations);
  const sections: string[] = [];

  if (corpus.length > 0) {
    sections.push(
      "### The law says\n" + corpus.map(formatCitationLine).join("\n"),
    );
  }
  if (upload.length > 0) {
    sections.push(
      "### Your document says\n" + upload.map(formatCitationLine).join("\n"),
    );
  }

  if (sections.length === 0) {
    return text;
  }

  return `${text.trim()}\n\n${sections.join("\n\n")}`;
}

export function formatAssistantContent(
  content: string,
  citations: Citation[] = [],
): string {
  const linked = linkifyNumericCitations(linkifyInlineCitations(content, citations), citations);
  return appendSourcesSection(linked, citations);
}

export function citationsFromMetadata(metadata: Record<string, unknown> | null): Citation[] {
  if (!metadata?.citations || !Array.isArray(metadata.citations)) {
    return [];
  }
  return metadata.citations as Citation[];
}
