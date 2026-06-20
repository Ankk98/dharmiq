import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";

import {
  createSession,
  listMessages,
  listSessions,
  postSessionMessage,
  sendChatMessage,
  type ChatMessage,
  type ChatSession,
  type Citation,
} from "@/lib/api";
import {
  citationsFromMetadata,
  formatAssistantContent,
} from "@/lib/citations";
import {
  getProgressView,
  setProgressView,
  type ProgressView,
} from "@/lib/chatPreferences";
import { useChatStream, type ProgressStep } from "@/hooks/useChatStream";

type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

type ChatRuntimeContextValue = {
  slowNotice: boolean;
  isRunning: boolean;
  lastCitations: Citation[];
  refreshSessions: () => Promise<ChatSession[]>;
  sessionId: string | null;
  progressView: ProgressView;
  setProgressView: (view: ProgressView) => void;
  progressSteps: ProgressStep[];
  streamStatus: ReturnType<typeof useChatStream>["status"];
  debugEvents: ReturnType<typeof useChatStream>["debugEvents"];
  awaitingClarification: boolean;
  forceAnswer: () => Promise<void>;
  streamError: string | null;
};

const ChatRuntimeContext = createContext<ChatRuntimeContextValue | null>(null);

const SLOW_THRESHOLD_MS = 30_000;
const STREAMING_MESSAGE_ID = "__streaming_assistant__";

function mapBackendMessage(message: ChatMessage, citations: Citation[] = []): StoredMessage {
  const role = message.role === "user" ? "user" : "assistant";
  let content = message.content;
  if (role === "assistant") {
    const messageCitations = citationsFromMetadata(message.metadata).length
      ? citationsFromMetadata(message.metadata)
      : citations;
    content = formatAssistantContent(content, messageCitations);
    if (message.role === "clarifier") {
      content = `**Clarification needed**\n\n${content}`;
    }
  }
  return { id: message.id, role, content };
}

function convertMessage(message: StoredMessage): ThreadMessageLike {
  return {
    id: message.id,
    role: message.role,
    content: [{ type: "text", text: message.content }],
  };
}

function ChatRuntimeInner({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);
  const [lastCitations, setLastCitations] = useState<Citation[]>([]);
  const [progressView, setProgressViewState] = useState<ProgressView>(getProgressView);
  const [awaitingClarification, setAwaitingClarification] = useState(false);
  const slowTimerRef = useRef<number | null>(null);
  const sessionIdRef = useRef<string | null>(sessionId);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const {
    status: streamStatus,
    progressSteps,
    streamingText,
    streamCitations,
    debugEvents,
    errorMessage: streamError,
    connect,
    disconnect,
    reset: resetStream,
  } = useChatStream(progressView);

  const clearSlowTimer = useCallback(() => {
    if (slowTimerRef.current != null) {
      window.clearTimeout(slowTimerRef.current);
      slowTimerRef.current = null;
    }
    setSlowNotice(false);
  }, []);

  const handleProgressViewChange = useCallback((view: ProgressView) => {
    setProgressView(view);
    setProgressViewState(view);
  }, []);

  const refreshSessions = useCallback(async () => {
    const rows = await listSessions();
    setSessions(rows);
    return rows;
  }, []);

  const detectClarification = useCallback((rows: ChatMessage[]) => {
    const last = rows.at(-1);
    setAwaitingClarification(last?.role === "clarifier");
  }, []);

  const loadMessages = useCallback(
    async (id: string) => {
      const rows = await listMessages(id);
      setMessages(rows.map((row) => mapBackendMessage(row)));
      detectClarification(rows);
    },
    [detectClarification],
  );

  useEffect(() => {
    void (async () => {
      let rows = await refreshSessions();
      if (rows.length === 0) {
        const created = await createSession();
        rows = [created];
        setSessions([created]);
      }
      const initial = rows[0]?.id ?? null;
      setSessionId(initial);
      if (initial) {
        await loadMessages(initial);
      }
    })();
  }, [loadMessages, refreshSessions]);

  const displayMessages = useMemo(() => {
    if (!isRunning || streamStatus !== "streaming" || !streamingText) {
      return messages;
    }
    const withoutStreaming = messages.filter((message) => message.id !== STREAMING_MESSAGE_ID);
    return [
      ...withoutStreaming,
      {
        id: STREAMING_MESSAGE_ID,
        role: "assistant" as const,
        content: formatAssistantContent(
          streamingText,
          streamCitations.map((item) => ({
            marker: item.marker,
            chunk_id: item.chunk_id,
            source_type: item.source_type ?? "corpus",
            document_id: item.document_id ?? item.chunk_id,
            document_title: item.document_title,
            quote_text: item.quote_text,
          })),
        ),
      },
    ];
  }, [isRunning, messages, streamCitations, streamStatus, streamingText]);

  const finalizeFromStream = useCallback(
    async (id: string, citations: Citation[]) => {
      setLastCitations(citations);
      await loadMessages(id);
      await refreshSessions();
    },
    [loadMessages, refreshSessions],
  );

  const runLegacyPipeline = useCallback(
    async (id: string, userText: string) => {
      const response = await sendChatMessage(id, userText);
      setLastCitations(response.citations);
      if (response.taking_longer_than_expected) {
        setSlowNotice(true);
      }
      setAwaitingClarification(response.needs_clarification);
      await loadMessages(id);
      await refreshSessions();
    },
    [loadMessages, refreshSessions],
  );

  const submitMessage = useCallback(
    async (userText: string, options?: { forceAnswer?: boolean }) => {
      const id = sessionIdRef.current;
      if (!id) {
        return;
      }

      setMessages((prev) => [
        ...prev.filter((message) => message.id !== STREAMING_MESSAGE_ID),
        { id: crypto.randomUUID(), role: "user", content: userText },
      ]);
      setIsRunning(true);
      setAwaitingClarification(false);
      clearSlowTimer();
      resetStream();
      slowTimerRef.current = window.setTimeout(() => setSlowNotice(true), SLOW_THRESHOLD_MS);

      try {
        const result = await postSessionMessage(id, userText, {
          forceAnswer: options?.forceAnswer,
        });

        if (result.mode === "async") {
          const streamResult = await connect(result.chat_request_id);
          const citations: Citation[] = streamResult.streamCitations.map((item) => ({
            marker: item.marker,
            chunk_id: item.chunk_id,
            source_type: item.source_type ?? "corpus",
            document_id: item.document_id ?? item.chunk_id,
            document_title: item.document_title,
            quote_text: item.quote_text,
          }));
          await finalizeFromStream(id, citations);
        } else {
          await runLegacyPipeline(id, userText);
        }
      } finally {
        disconnect();
        clearSlowTimer();
        setIsRunning(false);
        setMessages((prev) => prev.filter((message) => message.id !== STREAMING_MESSAGE_ID));
      }
    },
    [
      clearSlowTimer,
      connect,
      disconnect,
      finalizeFromStream,
      resetStream,
      runLegacyPipeline,
    ],
  );

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const firstPart = message.content[0];
      if (!firstPart || firstPart.type !== "text") {
        throw new Error("Only text messages are supported");
      }
      await submitMessage(firstPart.text);
    },
    [submitMessage],
  );

  const forceAnswer = useCallback(async () => {
    await submitMessage("Please answer with the information you have.", {
      forceAnswer: true,
    });
  }, [submitMessage]);

  const onSwitchToNewThread = useCallback(async () => {
    disconnect();
    resetStream();
    const created = await createSession();
    setSessions((prev) => [created, ...prev]);
    setSessionId(created.id);
    setMessages([]);
    setLastCitations([]);
    setAwaitingClarification(false);
    clearSlowTimer();
  }, [clearSlowTimer, disconnect, resetStream]);

  const onSwitchToThread = useCallback(
    async (threadId: string) => {
      disconnect();
      resetStream();
      setSessionId(threadId);
      setLastCitations([]);
      setAwaitingClarification(false);
      clearSlowTimer();
      await loadMessages(threadId);
    },
    [clearSlowTimer, disconnect, loadMessages, resetStream],
  );

  const threadListAdapter = useMemo(
    () => ({
      threadId: sessionId ?? undefined,
      threads: sessions.map((session) => ({
        id: session.id,
        status: "regular" as const,
        title: session.title ?? "New chat",
      })),
      archivedThreads: [],
      onSwitchToNewThread,
      onSwitchToThread,
    }),
    [sessionId, sessions, onSwitchToNewThread, onSwitchToThread],
  );

  const runtime = useExternalStoreRuntime({
    isRunning,
    messages: displayMessages,
    convertMessage,
    onNew,
    setMessages: (next) => setMessages([...next]),
    adapters: { threadList: threadListAdapter },
  });

  const contextValue = useMemo(
    () => ({
      slowNotice,
      isRunning,
      lastCitations,
      refreshSessions,
      sessionId,
      progressView,
      setProgressView: handleProgressViewChange,
      progressSteps,
      streamStatus,
      debugEvents,
      awaitingClarification,
      forceAnswer,
      streamError,
    }),
    [
      slowNotice,
      isRunning,
      lastCitations,
      refreshSessions,
      sessionId,
      progressView,
      handleProgressViewChange,
      progressSteps,
      streamStatus,
      debugEvents,
      awaitingClarification,
      forceAnswer,
      streamError,
    ],
  );

  return (
    <ChatRuntimeContext.Provider value={contextValue}>
      <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>
    </ChatRuntimeContext.Provider>
  );
}

export function ChatRuntimeProvider({ children }: { children: ReactNode }) {
  return <ChatRuntimeInner>{children}</ChatRuntimeInner>;
}

export function useChatRuntimeState(): ChatRuntimeContextValue {
  const context = useContext(ChatRuntimeContext);
  if (!context) {
    throw new Error("useChatRuntimeState must be used within ChatRuntimeProvider");
  }
  return context;
}
