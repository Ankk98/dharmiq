import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";

import {
  createSession,
  deleteSession,
  listChatRequestProgressEvents,
  listMessages,
  listSessions,
  postSessionMessage,
  editSessionMessage,
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
  isRefusalAnswer,
} from "@/lib/citations";
import { parseClarifierItems } from "@/lib/clarifier";
import {
  getProgressView,
  setProgressView,
  type ProgressView,
} from "@/lib/chatPreferences";
import { getStoredSessionId, setStoredSessionId, chatSessionPath, parseChatSessionId, isChatRoute } from "@/lib/chatSession";
import {
  applyProgressPayload,
  buildTurnProgress,
  chatRequestIdFromMetadata,
  type TurnProgress,
} from "@/lib/progress";
import {
  progressMessageId,
  STREAMING_MESSAGE_ID,
  STREAMING_PROGRESS_ID,
} from "@/lib/messageMeta";
import {
  buildMessageRepository,
  injectProgressMessages,
  type StoredMessage,
} from "@/lib/messageThread";
import { useChatStream } from "@/hooks/useChatStream";
import { ChatRuntimeContext } from "@/providers/chat-runtime-context";

const SLOW_THRESHOLD_MS = 30_000;

function citationsFromStream(items: StreamCitationPayload[]): Citation[] {
  return items.map((item) => ({
    marker: item.marker,
    chunk_id: item.chunk_id,
    source_type: item.source_type ?? "corpus",
    document_id: item.document_id ?? item.chunk_id,
    document_title: item.document_title,
    quote_text: item.quote_text,
    canonical_url: item.canonical_url ?? null,
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
): StoredMessage {
  if (message.role === "system") {
    return {
      id: message.id,
      role: "system",
      content: message.content,
    };
  }

  const chatRequestId = chatRequestIdFromMetadata(message.metadata);

  if (message.role === "clarifier") {
    const clarifierItems = parseClarifierItems(message.content, message.metadata);
    return {
      id: message.id,
      role: "assistant",
      content: message.content,
      chatRequestId,
      meta: {
        backendRole: "clarifier",
        clarifierReason:
          typeof message.metadata?.reason === "string"
            ? message.metadata.reason
            : undefined,
        clarifierQuestions: clarifierItems.map((item) => item.question),
        clarifierItems,
      },
    };
  }

  const role = message.role === "user" ? "user" : "assistant";
  let content = message.content;
  const agent =
    typeof message.metadata?.agent === "string" ? message.metadata.agent : undefined;

  if (role === "assistant") {
    const messageCitations = citationsFromMetadata(message.metadata).length
      ? citationsFromMetadata(message.metadata)
      : citations;
    content = formatAssistantContent(content, messageCitations);
  }

  return {
    id: message.id,
    role,
    content,
    chatRequestId,
    meta:
      role === "assistant"
        ? {
            backendRole: message.role,
            agent: agent ?? (isRefusalAnswer(message.content) ? "refusal" : undefined),
          }
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
  const navigate = useNavigate();
  const location = useLocation();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [slowNotice, setSlowNotice] = useState(false);
  const [lastCitations, setLastCitations] = useState<Citation[]>([]);
  const [progressView, setProgressViewState] = useState<ProgressView>(getProgressView);
  const [awaitingClarification, setAwaitingClarification] = useState(false);
  const [activeClarifierMessageId, setActiveClarifierMessageId] = useState<string | null>(
    null,
  );
  const slowTimerRef = useRef<number | null>(null);
  const attachPickerRef = useRef<(() => void) | null>(null);
  const sessionIdRef = useRef<string | null>(sessionId);
  const initStartedRef = useRef(false);
  const skipProgressViewRefreshRef = useRef(true);
  const urlSyncRef = useRef(false);
  const previousPathnameRef = useRef<string>(location.pathname);
  const activeAssistantIdRef = useRef<string | null>(null);
  const activeProgressIdRef = useRef<string | null>(null);
  const streamCitationsRef = useRef<StreamCitationPayload[]>([]);
  const streamingTextRef = useRef("");

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const selectSession = useCallback(
    (id: string | null, options?: { updateUrl?: boolean }) => {
      sessionIdRef.current = id;
      setSessionId(id);
      setStoredSessionId(id);
      if (options?.updateUrl !== false && id && isChatRoute(location.pathname)) {
        const target = chatSessionPath(id);
        if (location.pathname !== target) {
          navigate(target, { replace: true });
        }
      }
    },
    [location.pathname, navigate],
  );

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
        const progressId = activeProgressIdRef.current;
        if (!progressId) {
          return;
        }
        setMessages((prev) =>
          prev.map((message) =>
            message.id === progressId
              ? {
                  ...message,
                  progress: applyProgressPayload(message.progress, payload),
                }
              : message,
          ),
        );
      },
      onToken: (_token: string, accumulated: string) => {
        if (activeAssistantIdRef.current == null) {
          activeAssistantIdRef.current = STREAMING_MESSAGE_ID;
          setMessages((prev) => {
            if (prev.some((message) => message.id === STREAMING_MESSAGE_ID)) {
              return prev;
            }
            return [
              ...prev,
              {
                id: STREAMING_MESSAGE_ID,
                role: "assistant",
                content: "",
              },
            ];
          });
        }
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
        const progressId = activeProgressIdRef.current;
        if (!progressId) {
          return;
        }
        setMessages((prev) =>
          prev.map((message) =>
            message.id === progressId && message.progress
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
    const isClarifier = last?.role === "clarifier";
    setAwaitingClarification(isClarifier);
    setActiveClarifierMessageId(isClarifier && last ? last.id : null);
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
      const mapped = rows.map((row) => mapBackendMessage(row));
      setMessages(injectProgressMessages(mapped, progressByRequestId));
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

      const fromUrl = parseChatSessionId(location.pathname);
      const storedSessionId = getStoredSessionId();
      const initial =
        (fromUrl && rows.some((row) => row.id === fromUrl)
          ? fromUrl
          : storedSessionId && rows.some((row) => row.id === storedSessionId)
            ? storedSessionId
            : rows[0]?.id) ?? null;

      if (initial) {
        selectSession(initial, { updateUrl: false });
        if (isChatRoute(location.pathname)) {
          const target = chatSessionPath(initial);
          if (location.pathname !== target) {
            navigate(target, { replace: true });
          }
        }
        await loadMessages(initial);
      }
      urlSyncRef.current = true;
      previousPathnameRef.current = location.pathname;
    })();
  }, [loadMessages, location.pathname, navigate, refreshSessions, selectSession]);

  useEffect(() => {
    if (!urlSyncRef.current) {
      return;
    }

    if (previousPathnameRef.current === location.pathname) {
      return;
    }
    previousPathnameRef.current = location.pathname;

    const fromUrl = parseChatSessionId(location.pathname);
    if (!fromUrl || fromUrl === sessionIdRef.current) {
      return;
    }
    if (!sessions.some((session) => session.id === fromUrl)) {
      return;
    }

    void (async () => {
      disconnect();
      resetStream();
      activeAssistantIdRef.current = null;
      activeProgressIdRef.current = null;
      selectSession(fromUrl, { updateUrl: false });
      setLastCitations([]);
      setAwaitingClarification(false);
      setActiveClarifierMessageId(null);
      clearSlowTimer();
      await loadMessages(fromUrl);
    })();
  }, [
    clearSlowTimer,
    disconnect,
    loadMessages,
    location.pathname,
    resetStream,
    selectSession,
    sessions,
  ]);

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
      startRequest: () => Promise<
        | { mode: "async"; chat_request_id: string; user_message_id: string }
        | { mode: "sync" }
      >,
      options?: {
        legacyUserText?: string;
        userText?: string;
        prepareMessages?: (prev: StoredMessage[]) => StoredMessage[];
      },
    ) => {
      activeAssistantIdRef.current = null;
      activeProgressIdRef.current = STREAMING_PROGRESS_ID;
      streamCitationsRef.current = [];
      streamingTextRef.current = "";

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

        const stableProgressId = progressMessageId(result.chat_request_id);
        activeProgressIdRef.current = stableProgressId;

        setMessages((prev) => {
          const truncated = options?.prepareMessages ? options.prepareMessages(prev) : prev;
          const withoutStreaming = truncated.filter(
            (message) =>
              message.id !== STREAMING_MESSAGE_ID &&
              message.id !== STREAMING_PROGRESS_ID &&
              message.id !== stableProgressId,
          );

          const progressMessage: StoredMessage = {
            id: stableProgressId,
            role: "assistant",
            content: "",
            chatRequestId: result.chat_request_id,
            progress: { steps: [], status: "running" },
            meta: { backendRole: "progress" },
          };

          if (options?.userText) {
            return [
              ...withoutStreaming,
              {
                id: result.user_message_id,
                role: "user" as const,
                content: options.userText,
                chatRequestId: result.chat_request_id,
              },
              progressMessage,
            ];
          }

          return [...withoutStreaming, progressMessage];
        });

        const streamResult = await connect(result.chat_request_id);
        const citations = citationsFromStream(streamResult.streamCitations);
        await finalizeFromStream(id, citations);
      } finally {
        disconnect();
        clearSlowTimer();
        setIsRunning(false);
        activeAssistantIdRef.current = null;
        activeProgressIdRef.current = null;
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
          userText,
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

  const onEdit = useCallback(
    async (message: AppendMessage) => {
      const editedMessageId = message.sourceId;
      if (!editedMessageId) {
        return;
      }
      const firstPart = message.content[0];
      if (!firstPart || firstPart.type !== "text") {
        throw new Error("Only text messages can be edited");
      }
      const newText = firstPart.text.trim();
      if (!newText) {
        return;
      }

      const id = sessionIdRef.current;
      if (!id) {
        return;
      }

      await runAssistantPipeline(
        id,
        () => editSessionMessage(id, editedMessageId, newText),
        {
          prepareMessages: (prev) => {
            const userIndex = prev.findIndex(
              (row) => row.id === editedMessageId && row.role === "user",
            );
            if (userIndex === -1) {
              throw new Error("User message not found for edit");
            }
            return [
              ...prev.slice(0, userIndex),
              { ...prev[userIndex], role: "user", content: newText },
            ];
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
    activeProgressIdRef.current = null;
    clearSlowTimer();
    setLastCitations([]);
    setAwaitingClarification(false);
    setActiveClarifierMessageId(null);
    setMessages([]);

    const created = await createSession();
    setSessions((prev) => [created, ...prev]);
    selectSession(created.id, { updateUrl: false });
    navigate(chatSessionPath(created.id));
  }, [clearSlowTimer, disconnect, navigate, resetStream, selectSession]);

  const onSwitchToThread = useCallback(
    async (threadId: string) => {
      disconnect();
      resetStream();
      activeAssistantIdRef.current = null;
      activeProgressIdRef.current = null;
      selectSession(threadId);
      setLastCitations([]);
      setAwaitingClarification(false);
      setActiveClarifierMessageId(null);
      clearSlowTimer();
      navigate(chatSessionPath(threadId));
      await loadMessages(threadId);
    },
    [clearSlowTimer, disconnect, loadMessages, navigate, resetStream, selectSession],
  );

  const getMessageProgress = useCallback(
    (messageId: string) => messages.find((message) => message.id === messageId)?.progress,
    [messages],
  );

  const getMessageMeta = useCallback(
    (messageId: string) => messages.find((message) => message.id === messageId)?.meta,
    [messages],
  );

  const streamingMessageId = isRunning ? STREAMING_MESSAGE_ID : null;

  const hasThreadProgress = useMemo(
    () => messages.some((message) => (message.progress?.steps.length ?? 0) > 0),
    [messages],
  );

  const onDeleteThread = useCallback(
    async (threadId: string) => {
      await deleteSession(threadId);
      const rows = await refreshSessions();

      if (threadId !== sessionIdRef.current) {
        setSessions(rows);
        return;
      }

      disconnect();
      resetStream();
      activeAssistantIdRef.current = null;
      activeProgressIdRef.current = null;
      clearSlowTimer();
      setLastCitations([]);
      setAwaitingClarification(false);
      setActiveClarifierMessageId(null);

      if (rows.length > 0) {
        const next = rows[0];
        selectSession(next.id);
        navigate(chatSessionPath(next.id));
        await loadMessages(next.id);
        return;
      }

      const created = await createSession();
      setSessions([created]);
      selectSession(created.id);
      setMessages([]);
      navigate(chatSessionPath(created.id));
    },
    [clearSlowTimer, disconnect, loadMessages, navigate, refreshSessions, resetStream, selectSession],
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
      onDelete: onDeleteThread,
    }),
    [sessionId, sessions, onDeleteThread, onSwitchToNewThread, onSwitchToThread],
  );

  const messageRepository = useMemo(
    () => buildMessageRepository(messages, convertMessage),
    [messages],
  );

  const runtime = useExternalStoreRuntime({
    isRunning,
    messages,
    messageRepository,
    convertMessage,
    onNew,
    onEdit,
    onReload,
    setMessages: (next) => setMessages([...next]),
    adapters: { threadList: threadListAdapter },
  });

  const contextValue = useMemo(
    () => ({
      slowNotice,
      isRunning,
      lastCitations,
      sessions,
      refreshSessions,
      sessionId,
      progressView,
      setProgressView: handleProgressViewChange,
      hasThreadProgress,
      getMessageProgress,
      getMessageMeta,
      streamingMessageId,
      streamStatus,
      debugEvents,
      awaitingClarification,
      activeClarifierMessageId,
      forceAnswer,
      submitUserMessage: submitMessage,
      streamError,
      openAttachPicker,
      registerAttachPicker,
      refreshMessages,
    }),
    [
      slowNotice,
      isRunning,
      lastCitations,
      sessions,
      refreshSessions,
      sessionId,
      progressView,
      handleProgressViewChange,
      hasThreadProgress,
      getMessageProgress,
      getMessageMeta,
      streamingMessageId,
      streamStatus,
      debugEvents,
      awaitingClarification,
      activeClarifierMessageId,
      forceAnswer,
      submitMessage,
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
