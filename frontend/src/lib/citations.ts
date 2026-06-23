import type { Citation } from "@/lib/api";
import { documentViewerPath } from "@/lib/api";
import type { ReactNode } from "react";
import { Children, isValidElement } from "react";

const INLINE_CITATION_RE = /\[doc:([^|\]]+)\|chunk:([^\]]+)\]/g;
const NUMERIC_CITATION_RE = /\[(\d+)\]/g;

const REFUSAL_PHRASES = [
  "could not find sufficient sources",
  "insufficient sources",
  "to answer reliably",
] as const;

const DISCLAIMER_PHRASES = [
  "not legal advice",
  "general legal information",
  "consult a qualified",
  "qualified lawyer",
  "qualified advocate",
] as const;

function citationByMarker(citations: Citation[]): Map<number, Citation> {
  const map = new Map<number, Citation>();
  for (const citation of citations) {
    if (citation.marker != null) {
      map.set(citation.marker, citation);
    }
  }
  return map;
}

function citationViewerOptions(citation: Citation) {
  const options: {
    chunkId: string;
    sectionLabel?: string;
    quoteStart?: number;
    quoteEnd?: number;
  } = {
    chunkId: citation.chunk_id,
    sectionLabel: citation.section_label ?? undefined,
  };
  if (citation.quote_start_char != null && citation.quote_end_char != null) {
    options.quoteStart = citation.quote_start_char;
    options.quoteEnd = citation.quote_end_char;
  }
  return options;
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
    return `[${marker}](${documentViewerPath(citation.document_id, citation.source_type, citationViewerOptions(citation))})`;
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
    return `[${label}](${documentViewerPath(docId, sourceType, { chunkId })})`;
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
  const docLink = `[${label}${pages}](${documentViewerPath(citation.document_id, citation.source_type, citationViewerOptions(citation))})`;
  if (citation.source_type === "corpus" && citation.canonical_url) {
    return `- ${marker}${docLink} · [View on IndiaCode](${citation.canonical_url})`;
  }
  return `- ${marker}${docLink}`;
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

export function parseSourceTypeFromHref(
  href: string | undefined,
): "corpus" | "upload" | null {
  if (!href) {
    return null;
  }
  try {
    const url = href.startsWith("/")
      ? new URL(href, "http://local")
      : new URL(href);
    const sourceType = url.searchParams.get("source_type");
    if (sourceType === "upload" || sourceType === "corpus") {
      return sourceType;
    }
  } catch {
    return null;
  }
  return null;
}

export function isRefusalAnswer(text: string): boolean {
  const lowered = text.toLowerCase();
  return REFUSAL_PHRASES.some((phrase) => lowered.includes(phrase));
}

export function isDisclaimerBlockquote(text: string): boolean {
  const lowered = text.toLowerCase();
  return DISCLAIMER_PHRASES.some((phrase) => lowered.includes(phrase));
}

export function parseClarifierQuestions(content: string): string[] {
  return content
    .split("\n")
    .map((line) => line.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean);
}

export function flattenMarkdownChildren(children: ReactNode): string {
  return Children.toArray(children)
    .map((child) => {
      if (typeof child === "string" || typeof child === "number") {
        return String(child);
      }
      if (isValidElement<{ children?: ReactNode; href?: string }>(child)) {
        if (child.props.href) {
          return flattenMarkdownChildren(child.props.children);
        }
        return flattenMarkdownChildren(child.props.children);
      }
      return "";
    })
    .join("");
}

export function detectBlockquoteSourceType(
  children: ReactNode,
  text: string,
): "corpus" | "upload" {
  let foundUpload = false;
  let foundCorpus = false;

  const walk = (node: ReactNode): void => {
    Children.forEach(node, (child) => {
      if (!isValidElement<{ href?: string; children?: ReactNode }>(child)) {
        return;
      }
      const sourceType = parseSourceTypeFromHref(child.props.href);
      if (sourceType === "upload") {
        foundUpload = true;
      }
      if (sourceType === "corpus") {
        foundCorpus = true;
      }
      if (child.props.children) {
        walk(child.props.children);
      }
    });
  };

  walk(children);

  if (foundUpload && !foundCorpus) {
    return "upload";
  }
  if (foundCorpus && !foundUpload) {
    return "corpus";
  }

  const lowered = text.toLowerCase();
  if (
    lowered.includes("your document") ||
    lowered.includes("contract") ||
    lowered.includes("clause")
  ) {
    return "upload";
  }

  return "corpus";
}
