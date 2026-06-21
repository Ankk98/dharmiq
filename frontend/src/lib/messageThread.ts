import {
  ExportedMessageRepository,
  type ThreadMessageLike,
} from "@assistant-ui/react";

import type { TurnProgress } from "@/lib/progress";
import { progressMessageId, type StoredMessageMeta } from "@/lib/messageMeta";

export type StoredMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  chatRequestId?: string;
  progress?: TurnProgress;
  meta?: StoredMessageMeta;
};

function resolveParentId(messages: StoredMessage[], index: number): string | null {
  const message = messages[index];
  if (!message || index === 0) {
    return null;
  }

  if (message.meta?.backendRole === "progress" && message.chatRequestId) {
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      const candidate = messages[cursor];
      if (
        candidate?.role === "user" &&
        candidate.chatRequestId === message.chatRequestId
      ) {
        return candidate.id;
      }
    }
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      if (messages[cursor]?.role === "user") {
        return messages[cursor]!.id;
      }
    }
  }

  if (
    message.chatRequestId &&
    message.meta?.backendRole !== "progress" &&
    message.role === "assistant"
  ) {
    const progressId = progressMessageId(message.chatRequestId);
    const progressIndex = messages.findIndex((row) => row.id === progressId);
    if (progressIndex >= 0 && progressIndex < index) {
      return progressId;
    }
  }

  return messages[index - 1]?.id ?? null;
}

export function injectProgressMessages(
  messages: StoredMessage[],
  progressByRequestId: Map<string, TurnProgress>,
): StoredMessage[] {
  const inserted = new Set<string>();
  const result: StoredMessage[] = [];

  for (const message of messages) {
    if (message.meta?.backendRole === "progress") {
      if (message.chatRequestId) {
        inserted.add(message.chatRequestId);
      }
      result.push(message);
      continue;
    }

    const requestId = message.chatRequestId;
    const progress =
      requestId != null ? progressByRequestId.get(requestId) : undefined;
    const shouldInject =
      requestId != null &&
      progress != null &&
      progress.steps.length > 0 &&
      !inserted.has(requestId) &&
      message.role === "assistant";

    if (shouldInject) {
      inserted.add(requestId);
      result.push({
        id: progressMessageId(requestId),
        role: "assistant",
        content: "",
        chatRequestId: requestId,
        progress,
        meta: { backendRole: "progress" },
      });
    }

    result.push({ ...message, progress: undefined });
  }

  return result;
}

export function buildMessageRepository(
  messages: StoredMessage[],
  convertMessage: (message: StoredMessage) => ThreadMessageLike,
): ExportedMessageRepository {
  const items = messages.map((message, index) => ({
    parentId: resolveParentId(messages, index),
    message: {
      ...convertMessage(message),
      id: message.id,
    },
  }));

  return ExportedMessageRepository.fromBranchableArray(items, {
    headId: messages.at(-1)?.id,
  });
}
