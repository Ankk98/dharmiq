export type MessageRole = "user" | "assistant" | "clarifier" | "validator";

export type ChatSession = {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  user_id: string;
  role: MessageRole;
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type Citation = {
  chunk_id: string;
  source_type: "corpus" | "upload";
  document_id: string;
  document_title: string;
  chunk_index: number;
  page_start?: number | null;
  page_end?: number | null;
};

export type ChatPipelineResponse = {
  chat_request_id: string;
  status: "pending" | "running" | "completed" | "failed";
  needs_clarification: boolean;
  followup_questions: string[];
  answer: string | null;
  citations: Citation[];
  final_warning: string | null;
  taking_longer_than_expected: boolean;
  messages: ChatMessage[];
  error_message: string | null;
};

export type UserProfile = {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
};

const TOKEN_KEY = "dharmiq_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body !== undefined && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string | { msg?: string }[] };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      } else if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
        detail = payload.detail[0].msg;
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams({ username: email, password });
  const response = await fetch("/api/auth/jwt/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Login failed");
  }
  const data = (await response.json()) as { access_token: string };
  setToken(data.access_token);
  return data.access_token;
}

export async function register(email: string, password: string): Promise<UserProfile> {
  return apiFetch<UserProfile>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function fetchCurrentUser(): Promise<UserProfile> {
  return apiFetch<UserProfile>("/api/users/me");
}

export async function listSessions(): Promise<ChatSession[]> {
  return apiFetch<ChatSession[]>("/api/chat/sessions");
}

export async function createSession(title?: string): Promise<ChatSession> {
  return apiFetch<ChatSession>("/api/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}

export async function listMessages(sessionId: string): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(`/api/chat/sessions/${sessionId}/messages`);
}

export async function sendChatMessage(
  sessionId: string,
  message: string,
  signal?: AbortSignal,
): Promise<ChatPipelineResponse> {
  return apiFetch<ChatPipelineResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  });
}

export function documentFileUrl(documentId: string, sourceType: "corpus" | "upload"): string {
  return `/api/docs/${documentId}/file?source_type=${sourceType}`;
}

export function documentViewerPath(documentId: string, sourceType: "corpus" | "upload"): string {
  return `/docs/${documentId}?source_type=${sourceType}`;
}
