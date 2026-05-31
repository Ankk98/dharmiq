import type { Citation } from "@/lib/api";
import { documentViewerPath } from "@/lib/api";

const INLINE_CITATION_RE = /\[doc:([^|\]]+)\|chunk:([^\]]+)\]/g;

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

export function appendSourcesSection(text: string, citations: Citation[]): string {
  if (citations.length === 0) {
    return text;
  }

  const unique = new Map<string, Citation>();
  for (const citation of citations) {
    unique.set(`${citation.source_type}:${citation.document_id}`, citation);
  }

  const lines = Array.from(unique.values()).map((citation) => {
    const pages =
      citation.page_start != null
        ? ` (pp. ${citation.page_start}${citation.page_end ? `–${citation.page_end}` : ""})`
        : "";
    return `- [${citation.document_title}${pages}](${documentViewerPath(citation.document_id, citation.source_type)})`;
  });

  return `${text.trim()}\n\n### Sources\n${lines.join("\n")}`;
}

export function formatAssistantContent(
  content: string,
  citations: Citation[] = [],
): string {
  return appendSourcesSection(linkifyInlineCitations(content, citations), citations);
}
