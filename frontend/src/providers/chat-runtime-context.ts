import { createContext } from "react";

import type { ProgressView } from "@/lib/chatPreferences";
import type { Citation, ChatSession } from "@/lib/api";
import type { TurnProgress } from "@/lib/progress";
import type { useChatStream } from "@/hooks/useChatStream";

export type ChatRuntimeContextValue = {
  slowNotice: boolean;
  isRunning: boolean;
  lastCitations: Citation[];
  refreshSessions: () => Promise<ChatSession[]>;
  sessionId: string | null;
  progressView: ProgressView;
  setProgressView: (view: ProgressView) => void;
  getMessageProgress: (messageId: string) => TurnProgress | undefined;
  streamStatus: ReturnType<typeof useChatStream>["status"];
  debugEvents: ReturnType<typeof useChatStream>["debugEvents"];
  awaitingClarification: boolean;
  forceAnswer: () => Promise<void>;
  streamError: string | null;
  openAttachPicker: () => void;
  registerAttachPicker: (handler: (() => void) | null) => void;
  refreshMessages: () => Promise<void>;
};

export const ChatRuntimeContext = createContext<ChatRuntimeContextValue | null>(
  null,
);
