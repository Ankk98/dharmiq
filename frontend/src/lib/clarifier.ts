export type ClarifierItem = {
  question: string;
  why?: string;
  options: string[];
};

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
  _content: string,
  metadata?: Record<string, unknown> | null,
): ClarifierItem[] {
  return parseMetadataItems(metadata);
}
