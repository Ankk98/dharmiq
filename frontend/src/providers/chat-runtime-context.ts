import { createContext } from "react";

import type { ProgressView } from "@/lib/chatPreferences";
import type { Citation, ChatSession } from "@/lib/api";
import type { StoredMessageMeta } from "@/lib/messageMeta";
import type { TurnProgress } from "@/lib/progress";
import type { useChatStream } from "@/hooks/useChatStream";

export type ChatRuntimeContextValue = {
  slowNotice: boolean;
  isRunning: boolean;
  lastCitations: Citation[];
  sessions: ChatSession[];
  refreshSessions: () => Promise<ChatSession[]>;
  sessionId: string | null;
  progressView: ProgressView;
  setProgressView: (view: ProgressView) => void;
  hasThreadProgress: boolean;
  getMessageProgress: (messageId: string) => TurnProgress | undefined;
  getMessageMeta: (messageId: string) => StoredMessageMeta | undefined;
  streamingMessageId: string | null;
  streamStatus: ReturnType<typeof useChatStream>["status"];
  debugEvents: ReturnType<typeof useChatStream>["debugEvents"];
  awaitingClarification: boolean;
  activeClarifierMessageId: string | null;
  forceAnswer: () => Promise<void>;
  submitUserMessage: (text: string) => Promise<void>;
  streamError: string | null;
  openAttachPicker: () => void;
  registerAttachPicker: (handler: (() => void) | null) => void;
  refreshMessages: () => Promise<void>;
};

export const ChatRuntimeContext = createContext<ChatRuntimeContextValue | null>(
  null,
);
