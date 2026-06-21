import {
  useCallback,
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
  listChatRequestProgressEvents,
  listMessages,
  listSessions,
  postSessionMessage,
  retrySessionMessage,
  sendChatMessage,
  type ChatMessage,
  type ChatSession,
  type Citation,
  type StreamCitationPayload,
  type StreamProgressPayload,
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
import { getStoredSessionId, setStoredSessionId } from "@/lib/chatSession";
import {
  applyProgressPayload,
  buildTurnProgress,
  chatRequestIdFromMetadata,
  type TurnProgress,
} from "@/lib/progress";
import { useChatStream } from "@/hooks/useChatStream";
import { ChatRuntimeContext } from "@/providers/chat-runtime-context";

type StoredMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  chatRequestId?: string;
  progress?: TurnProgress;
};

const SLOW_THRESHOLD_MS = 30_000;
const STREAMING_MESSAGE_ID = "__streaming_assistant__";

function citationsFromStream(items: StreamCitationPayload[]): Citation[] {
  return items.map((item) => ({
    marker: item.marker,
    chunk_id: item.chunk_id,
    source_type: item.source_type ?? "corpus",
    document_id: item.document_id ?? item.chunk_id,
    document_title: item.document_title,
    quote_text: item.quote_text,
  }));
}

async function loadProgressForRequestIds(
  requestIds: string[],
  view: ProgressView,
): Promise<Map<string, TurnProgress>> {
  const entries = await Promise.all(
    requestIds.map(async (requestId) => {
      const payloads = await listChatRequestProgressEvents(requestId, view);
      return [requestId, buildTurnProgress(payloads)] as const;
    }),
  );
  return new Map(entries);
}

function mapBackendMessage(
  message: ChatMessage,
  citations: Citation[] = [],
  progressByRequestId: Map<string, TurnProgress> = new Map(),
): StoredMessage {
  if (message.role === "system") {
    return {
      id: message.id,
      role: "system",
      content: message.content,
    };
  }

  const role = message.role === "user" ? "user" : "assistant";
  const chatRequestId = chatRequestIdFromMetadata(message.metadata);
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
  return {
    id: message.id,
    role,
    content,
    chatRequestId,
    progress:
      role === "assistant" && chatRequestId
        ? progressByRequestId.get(chatRequestId)
        : undefined,
  };
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
  const attachPickerRef = useRef<(() => void) | null>(null);
  const sessionIdRef = useRef<string | null>(sessionId);
  const initStartedRef = useRef(false);
  const skipProgressViewRefreshRef = useRef(true);
  const activeAssistantIdRef = useRef<string | null>(null);
  const streamCitationsRef = useRef<StreamCitationPayload[]>([]);
  const streamingTextRef = useRef("");

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const selectSession = useCallback((id: string | null) => {
    sessionIdRef.current = id;
    setSessionId(id);
    setStoredSessionId(id);
  }, []);

  const updateActiveAssistantContent = useCallback((text: string, citations: Citation[]) => {
    const assistantId = activeAssistantIdRef.current;
    if (!assistantId) {
      return;
    }
    setMessages((prev) =>
      prev.map((message) =>
        message.id === assistantId
          ? { ...message, content: formatAssistantContent(text, citations) }
          : message,
      ),
    );
  }, []);

  const streamCallbacks = useMemo(
    () => ({
      onProgress: (payload: StreamProgressPayload) => {
        const assistantId = activeAssistantIdRef.current;
        if (!assistantId) {
          return;
        }
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  progress: applyProgressPayload(message.progress, payload),
                }
              : message,
          ),
        );
      },
      onToken: (_token: string, accumulated: string) => {
        streamingTextRef.current = accumulated;
        updateActiveAssistantContent(
          accumulated,
          citationsFromStream(streamCitationsRef.current),
        );
      },
      onCitation: (citation: StreamCitationPayload) => {
        streamCitationsRef.current.push(citation);
        if (streamingTextRef.current) {
          updateActiveAssistantContent(
            streamingTextRef.current,
            citationsFromStream(streamCitationsRef.current),
          );
        }
      },
      onDone: () => {
        const assistantId = activeAssistantIdRef.current;
        if (!assistantId) {
          return;
        }
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId && message.progress
              ? { ...message, progress: { ...message.progress, status: "completed" } }
              : message,
          ),
        );
      },
    }),
    [updateActiveAssistantContent],
  );

  const {
    status: streamStatus,
    debugEvents,
    errorMessage: streamError,
    connect,
    disconnect,
    reset: resetStream,
  } = useChatStream(streamCallbacks);

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

  const registerAttachPicker = useCallback((handler: (() => void) | null) => {
    attachPickerRef.current = handler;
  }, []);

  const openAttachPicker = useCallback(() => {
    attachPickerRef.current?.();
  }, []);

  const detectClarification = useCallback((rows: ChatMessage[]) => {
    const last = rows.at(-1);
    setAwaitingClarification(last?.role === "clarifier");
  }, []);

  const loadMessages = useCallback(
    async (id: string, view: ProgressView = progressView) => {
      const rows = await listMessages(id);
      const requestIds = [
        ...new Set(
          rows
            .map((row) => chatRequestIdFromMetadata(row.metadata))
            .filter((value): value is string => Boolean(value)),
        ),
      ];
      const progressByRequestId =
        requestIds.length > 0 ? await loadProgressForRequestIds(requestIds, view) : new Map();
      setMessages(rows.map((row) => mapBackendMessage(row, [], progressByRequestId)));
      detectClarification(rows);
    },
    [detectClarification, progressView],
  );

  const refreshMessages = useCallback(async () => {
    const id = sessionIdRef.current;
    if (!id || isRunning) {
      return;
    }
    await loadMessages(id);
  }, [isRunning, loadMessages]);

  useEffect(() => {
    if (skipProgressViewRefreshRef.current) {
      skipProgressViewRefreshRef.current = false;
      return;
    }
    const id = sessionIdRef.current;
    if (!id || isRunning) {
      return;
    }
    void loadMessages(id, progressView);
  }, [isRunning, loadMessages, progressView]);

  useEffect(() => {
    if (initStartedRef.current) {
      return;
    }
    initStartedRef.current = true;

    void (async () => {
      let rows = await refreshSessions();
      if (rows.length === 0) {
        const created = await createSession();
        rows = [created];
        setSessions([created]);
      }

      const storedSessionId = getStoredSessionId();
      const initial =
        (storedSessionId && rows.some((row) => row.id === storedSessionId)
          ? storedSessionId
          : rows[0]?.id) ?? null;
      selectSession(initial);
      if (initial) {
        await loadMessages(initial);
      }
    })();
  }, [loadMessages, refreshSessions, selectSession]);

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

  const runAssistantPipeline = useCallback(
    async (
      id: string,
      startRequest: () => Promise<{ mode: "async"; chat_request_id: string } | { mode: "sync" }>,
      options?: { legacyUserText?: string; prepareMessages?: (prev: StoredMessage[]) => StoredMessage[] },
    ) => {
      const assistantMessageId = STREAMING_MESSAGE_ID;
      activeAssistantIdRef.current = assistantMessageId;
      streamCitationsRef.current = [];
      streamingTextRef.current = "";

      setMessages((prev) => {
        const next = options?.prepareMessages ? options.prepareMessages(prev) : prev;
        return [
          ...next.filter((message) => message.id !== STREAMING_MESSAGE_ID),
          {
            id: assistantMessageId,
            role: "assistant",
            content: "",
            progress: { steps: [], status: "running" },
          },
        ];
      });
      setIsRunning(true);
      setAwaitingClarification(false);
      clearSlowTimer();
      resetStream();
      slowTimerRef.current = window.setTimeout(() => setSlowNotice(true), SLOW_THRESHOLD_MS);

      try {
        const result = await startRequest();

        if (result.mode === "sync") {
          await loadMessages(id);
          if (options?.legacyUserText) {
            await runLegacyPipeline(id, options.legacyUserText);
          }
          return;
        }

        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantMessageId
              ? { ...message, chatRequestId: result.chat_request_id }
              : message,
          ),
        );

        const streamResult = await connect(result.chat_request_id);
        const citations = citationsFromStream(streamResult.streamCitations);
        await finalizeFromStream(id, citations);
      } finally {
        disconnect();
        clearSlowTimer();
        setIsRunning(false);
        activeAssistantIdRef.current = null;
        streamCitationsRef.current = [];
        streamingTextRef.current = "";
      }
    },
    [
      clearSlowTimer,
      connect,
      disconnect,
      finalizeFromStream,
      loadMessages,
      resetStream,
      runLegacyPipeline,
    ],
  );

  const submitMessage = useCallback(
    async (userText: string, options?: { forceAnswer?: boolean }) => {
      const id = sessionIdRef.current;
      if (!id) {
        return;
      }

      await runAssistantPipeline(
        id,
        () =>
          postSessionMessage(id, userText, {
            forceAnswer: options?.forceAnswer,
          }),
        {
          legacyUserText: userText,
          prepareMessages: (prev) => [
            ...prev,
            { id: crypto.randomUUID(), role: "user", content: userText },
          ],
        },
      );
    },
    [runAssistantPipeline],
  );

  const onReload = useCallback(
    async (parentId: string | null) => {
      const id = sessionIdRef.current;
      if (!id || !parentId) {
        return;
      }

      await runAssistantPipeline(
        id,
        () => retrySessionMessage(id, parentId),
        {
          prepareMessages: (prev) => {
            const userIndex = prev.findIndex(
              (message) => message.id === parentId && message.role === "user",
            );
            if (userIndex === -1) {
              throw new Error("User message not found for retry");
            }
            return prev.slice(0, userIndex + 1);
          },
        },
      );
    },
    [runAssistantPipeline],
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
    activeAssistantIdRef.current = null;
    const created = await createSession();
    setSessions((prev) => [created, ...prev]);
    selectSession(created.id);
    setMessages([]);
    setLastCitations([]);
    setAwaitingClarification(false);
    clearSlowTimer();
  }, [clearSlowTimer, disconnect, resetStream, selectSession]);

  const onSwitchToThread = useCallback(
    async (threadId: string) => {
      disconnect();
      resetStream();
      activeAssistantIdRef.current = null;
      selectSession(threadId);
      setLastCitations([]);
      setAwaitingClarification(false);
      clearSlowTimer();
      await loadMessages(threadId);
    },
    [clearSlowTimer, disconnect, loadMessages, resetStream, selectSession],
  );

  const getMessageProgress = useCallback(
    (messageId: string) => messages.find((message) => message.id === messageId)?.progress,
    [messages],
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
    messages,
    convertMessage,
    onNew,
    onReload,
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
      getMessageProgress,
      streamStatus,
      debugEvents,
      awaitingClarification,
      forceAnswer,
      streamError,
      openAttachPicker,
      registerAttachPicker,
      refreshMessages,
    }),
    [
      slowNotice,
      isRunning,
      lastCitations,
      refreshSessions,
      sessionId,
      progressView,
      handleProgressViewChange,
      getMessageProgress,
      streamStatus,
      debugEvents,
      awaitingClarification,
      forceAnswer,
      streamError,
      openAttachPicker,
      registerAttachPicker,
      refreshMessages,
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
