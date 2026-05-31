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
  sendChatMessage,
  type ChatMessage,
  type ChatSession,
  type Citation,
} from "@/lib/api";
import { formatAssistantContent } from "@/lib/citations";

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
};

const ChatRuntimeContext = createContext<ChatRuntimeContextValue | null>(null);

const SLOW_THRESHOLD_MS = 30_000;

function mapBackendMessage(message: ChatMessage, citations: Citation[] = []): StoredMessage {
  const role = message.role === "user" ? "user" : "assistant";
  let content = message.content;
  if (role === "assistant") {
    const messageCitations =
      (message.metadata?.citations as Citation[] | undefined) ?? citations;
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
  const slowTimerRef = useRef<number | null>(null);

  const clearSlowTimer = useCallback(() => {
    if (slowTimerRef.current != null) {
      window.clearTimeout(slowTimerRef.current);
      slowTimerRef.current = null;
    }
    setSlowNotice(false);
  }, []);

  const refreshSessions = useCallback(async () => {
    const rows = await listSessions();
    setSessions(rows);
    return rows;
  }, []);

  const loadMessages = useCallback(async (id: string) => {
    const rows = await listMessages(id);
    setMessages(rows.map((row) => mapBackendMessage(row)));
  }, []);

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

  const onNew = useCallback(
    async (message: AppendMessage) => {
      if (!sessionId) {
        return;
      }
      const firstPart = message.content[0];
      if (!firstPart || firstPart.type !== "text") {
        throw new Error("Only text messages are supported");
      }

      const userText = firstPart.text;
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", content: userText }]);
      setIsRunning(true);
      clearSlowTimer();
      slowTimerRef.current = window.setTimeout(() => setSlowNotice(true), SLOW_THRESHOLD_MS);

      try {
        const response = await sendChatMessage(sessionId, userText);
        setLastCitations(response.citations);
        if (response.taking_longer_than_expected) {
          setSlowNotice(true);
        }

        const mapped = response.messages.map((row) =>
          mapBackendMessage(
            row,
            row.role === "assistant" ? response.citations : [],
          ),
        );
        setMessages(mapped);
        await refreshSessions();
      } finally {
        clearSlowTimer();
        setIsRunning(false);
      }
    },
    [sessionId, clearSlowTimer, refreshSessions],
  );

  const onSwitchToNewThread = useCallback(async () => {
    const created = await createSession();
    setSessions((prev) => [created, ...prev]);
    setSessionId(created.id);
    setMessages([]);
    setLastCitations([]);
    clearSlowTimer();
  }, [clearSlowTimer]);

  const onSwitchToThread = useCallback(
    async (threadId: string) => {
      setSessionId(threadId);
      setLastCitations([]);
      clearSlowTimer();
      await loadMessages(threadId);
    },
    [clearSlowTimer, loadMessages],
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
    setMessages: (next) => setMessages([...next]),
    adapters: { threadList: threadListAdapter },
  });

  const contextValue = useMemo(
    () => ({ slowNotice, isRunning, lastCitations, refreshSessions }),
    [slowNotice, isRunning, lastCitations, refreshSessions],
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
