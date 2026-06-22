import { type MouseEvent, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { useDocumentPanel } from "@/hooks/useDocumentPanel";
import { parseSourceTypeFromHref } from "@/lib/citations";

type DocumentCitationLinkProps = {
  href: string;
  className?: string;
  children: ReactNode;
};

function parseQuoteSpan(
  searchParams: URLSearchParams,
): { quoteStart?: number; quoteEnd?: number } {
  const startRaw = searchParams.get("qstart");
  const endRaw = searchParams.get("qend");
  if (startRaw == null || endRaw == null) {
    return {};
  }
  const quoteStart = Number(startRaw);
  const quoteEnd = Number(endRaw);
  if (!Number.isInteger(quoteStart) || !Number.isInteger(quoteEnd) || quoteStart < 0 || quoteEnd <= quoteStart) {
    return {};
  }
  return { quoteStart, quoteEnd };
}

function parseDocumentHref(href: string): {
  documentId: string;
  sourceType: "corpus" | "upload";
  chunkId?: string;
  quoteStart?: number;
  quoteEnd?: number;
  sectionLabel?: string;
} | null {
  try {
    const url = href.startsWith("/")
      ? new URL(href, "http://local")
      : new URL(href);
    const match = url.pathname.match(/^\/docs\/([^/]+)$/);
    if (!match) {
      return null;
    }
    const sourceType = parseSourceTypeFromHref(href) ?? "corpus";
    const { quoteStart, quoteEnd } = parseQuoteSpan(url.searchParams);
    return {
      documentId: match[1],
      sourceType,
      chunkId: url.searchParams.get("chunk") ?? undefined,
      quoteStart,
      quoteEnd,
      sectionLabel: url.searchParams.get("section") ?? undefined,
    };
  } catch {
    return null;
  }
}

export function DocumentCitationLink({
  href,
  className,
  children,
}: DocumentCitationLinkProps) {
  const location = useLocation();
  const { openDocument } = useDocumentPanel();
  const parsed = parseDocumentHref(href);

  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!parsed || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    openDocument(parsed, {
      returnTo: `${location.pathname}${location.search}`,
    });
  };

  return (
    <Link to={href} className={className} onClick={handleClick}>
      {children}
    </Link>
  );
}
