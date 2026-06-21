import type { MessageRole } from "@/lib/api";
import { isRefusalAnswer } from "@/lib/citations";

import type { ClarifierItem } from "@/lib/clarifier";

export const STREAMING_MESSAGE_ID = "__streaming_assistant__";
export const STREAMING_PROGRESS_ID = "__streaming_progress__";

export function progressMessageId(chatRequestId: string): string {
  return `progress:${chatRequestId}`;
}

export type StoredMessageMeta = {
  backendRole?: MessageRole | "progress";
  agent?: string;
  clarifierReason?: string;
  clarifierQuestions?: string[];
  clarifierItems?: ClarifierItem[];
};

export type MessagePresentation =
  | { kind: "progress" }
  | { kind: "clarifier"; reason?: string; items: ClarifierItem[] }
  | { kind: "refusal" }
  | { kind: "answer" };

export function messagePresentation(
  content: string,
  meta?: StoredMessageMeta,
): MessagePresentation {
  if (meta?.backendRole === "progress") {
    return { kind: "progress" };
  }
  if (meta?.backendRole === "clarifier") {
    return {
      kind: "clarifier",
      reason: meta.clarifierReason,
      items:
        meta.clarifierItems ??
        (meta.clarifierQuestions ?? []).map((question) => ({
          question,
          options: [],
        })),
    };
  }
  if (meta?.agent === "refusal" || isRefusalAnswer(content)) {
    return { kind: "refusal" };
  }
  return { kind: "answer" };
}
