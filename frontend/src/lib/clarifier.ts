export type ClarifierItem = {
  question: string;
  why?: string;
  options: string[];
};

function splitQuestionAndWhy(text: string): { question: string; why?: string } {
  const parts = text.split(/\s+[—–-]\s+/);
  if (parts.length >= 2) {
    return {
      question: parts[0]?.trim() ?? text,
      why: parts.slice(1).join(" — ").trim() || undefined,
    };
  }
  return { question: text.trim() };
}

function parseMetadataItems(metadata: Record<string, unknown> | null | undefined): ClarifierItem[] {
  const raw = metadata?.followup_items;
  if (!Array.isArray(raw)) {
    return [];
  }

  const items: ClarifierItem[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") {
      continue;
    }
    const record = entry as Record<string, unknown>;
    const question = typeof record.question === "string" ? record.question.trim() : "";
    if (!question) {
      continue;
    }
    const options = Array.isArray(record.options)
      ? record.options
          .map((value) => (typeof value === "string" ? value.trim() : ""))
          .filter(Boolean)
      : [];
    const why = typeof record.why === "string" ? record.why.trim() : undefined;
    items.push({ question, why: why || undefined, options });
  }
  return items;
}

export function parseClarifierItems(
  content: string,
  metadata?: Record<string, unknown> | null,
): ClarifierItem[] {
  const fromMetadata = parseMetadataItems(metadata);
  if (fromMetadata.length > 0) {
    return fromMetadata;
  }

  return content
    .split("\n")
    .map((line) => line.replace(/^[-*]\s*/, "").trim())
    .filter(Boolean)
    .map((line) => {
      const { question, why } = splitQuestionAndWhy(line);
      return { question, why, options: [] };
    });
}
