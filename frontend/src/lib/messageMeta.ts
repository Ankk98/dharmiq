import type { MessageRole } from "@/lib/api";
import { isRefusalAnswer } from "@/lib/citations";

export const STREAMING_MESSAGE_ID = "__streaming_assistant__";

export type StoredMessageMeta = {
  backendRole?: MessageRole;
  agent?: string;
  clarifierReason?: string;
  clarifierQuestions?: string[];
};

export type MessagePresentation =
  | { kind: "clarifier"; reason?: string; questions: string[] }
  | { kind: "refusal" }
  | { kind: "answer" };

export function messagePresentation(
  content: string,
  meta?: StoredMessageMeta,
): MessagePresentation {
  if (meta?.backendRole === "clarifier") {
    return {
      kind: "clarifier",
      reason: meta.clarifierReason,
      questions: meta.clarifierQuestions ?? [],
    };
  }
  if (meta?.agent === "refusal" || isRefusalAnswer(content)) {
    return { kind: "refusal" };
  }
  return { kind: "answer" };
}
