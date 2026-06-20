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
  marker?: number;
  chunk_id: string;
  source_type: "corpus" | "upload";
  document_id: string;
  document_title: string;
  chunk_index?: number;
  section_label?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  quote_text?: string | null;
};

export type ChatRequestPendingResponse = {
  chat_request_id: string;
  status: "pending";
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

export type UserUpload = {
  id: string;
  user_id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  content_hash: string;
  created_at: string;
  deleted_at: string | null;
  indexed: boolean;
};

export type SessionAttachment = {
  session_id: string;
  upload_id: string;
  attached_at: string;
};

export type StreamProgressPayload = {
  seq: number;
  step_id?: string;
  label: string;
  status: "running" | "completed" | "failed";
  agent?: string;
  chunk_count?: number;
  preview?: string[];
  rerank_scores?: number[];
  queries?: string[];
  validator_issues?: string[];
  chunk_snippets?: string[];
  token_breakdown?: Record<string, number>;
};

export type StreamAnswerTokenPayload = {
  seq: number;
  token: string;
  citation_markers: number[];
};

export type StreamCitationPayload = {
  seq: number;
  marker: number;
  chunk_id: string;
  document_title: string;
  quote_text?: string;
  source_type?: "corpus" | "upload";
  document_id?: string;
};

export type StreamDonePayload = {
  seq: number;
  status: string;
  message_id?: string;
  citations?: Citation[];
  total_tokens?: number;
};

export type StreamErrorPayload = {
  seq: number;
  code: string;
  message: string;
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

export type PostSessionMessageResult =
  | { mode: "async"; chat_request_id: string }
  | { mode: "sync"; message: ChatMessage };

export async function postSessionMessage(
  sessionId: string,
  content: string,
  options?: { forceAnswer?: boolean; signal?: AbortSignal },
): Promise<PostSessionMessageResult> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      content,
      force_answer: options?.forceAnswer ?? false,
    }),
    signal: options?.signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // ignore
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 202) {
    const body = (await response.json()) as ChatRequestPendingResponse;
    return { mode: "async", chat_request_id: body.chat_request_id };
  }

  const message = (await response.json()) as ChatMessage;
  return { mode: "sync", message };
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

export function chatRequestStreamUrl(
  requestId: string,
  options?: { afterSeq?: number; view?: "concise" | "detailed" },
): string {
  const params = new URLSearchParams();
  if (options?.afterSeq != null && options.afterSeq > 0) {
    params.set("after_seq", String(options.afterSeq));
  }
  if (options?.view === "detailed") {
    params.set("view", "detailed");
  }
  const query = params.toString();
  return `/api/chat/requests/${requestId}/stream${query ? `?${query}` : ""}`;
}

export async function listChatRequestProgressEvents(
  requestId: string,
  view: "concise" | "detailed" = "concise",
): Promise<StreamProgressPayload[]> {
  const params = new URLSearchParams();
  if (view === "detailed") {
    params.set("view", "detailed");
  }
  const query = params.toString();
  return apiFetch<StreamProgressPayload[]>(
    `/api/chat/requests/${requestId}/events${query ? `?${query}` : ""}`,
  );
}

export async function listUploads(): Promise<UserUpload[]> {
  return apiFetch<UserUpload[]>("/api/uploads");
}

export async function uploadFile(file: File): Promise<UserUpload> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<UserUpload>("/api/uploads", {
    method: "POST",
    body: form,
  });
}

export async function deleteUpload(uploadId: string): Promise<void> {
  await apiFetch<void>(`/api/uploads/${uploadId}`, { method: "DELETE" });
}

export async function listSessionAttachments(sessionId: string): Promise<SessionAttachment[]> {
  return apiFetch<SessionAttachment[]>(`/api/chat/sessions/${sessionId}/attachments`);
}

export async function attachUploads(
  sessionId: string,
  uploadIds: string[],
): Promise<SessionAttachment[]> {
  return apiFetch<SessionAttachment[]>(`/api/chat/sessions/${sessionId}/attachments`, {
    method: "POST",
    body: JSON.stringify({ upload_ids: uploadIds }),
  });
}

export async function detachUpload(sessionId: string, uploadId: string): Promise<void> {
  await apiFetch<void>(`/api/chat/sessions/${sessionId}/attachments/${uploadId}`, {
    method: "DELETE",
  });
}

export function documentFileUrl(documentId: string, sourceType: "corpus" | "upload"): string {
  return `/api/docs/${documentId}/file?source_type=${sourceType}`;
}

export function documentViewerPath(documentId: string, sourceType: "corpus" | "upload"): string {
  return `/docs/${documentId}?source_type=${sourceType}`;
}

export type ParsedSSEEvent =
  | { type: "progress"; data: StreamProgressPayload }
  | { type: "answer_token"; data: StreamAnswerTokenPayload }
  | { type: "citation"; data: StreamCitationPayload }
  | { type: "done"; data: StreamDonePayload }
  | { type: "error"; data: StreamErrorPayload };

export function parseSSEChunk(buffer: string): { events: ParsedSSEEvent[]; remainder: string } {
  const events: ParsedSSEEvent[] = [];
  const blocks = buffer.split("\n\n");
  const remainder = blocks.pop() ?? "";

  for (const block of blocks) {
    if (!block.trim()) {
      continue;
    }
    let eventType = "message";
    let dataLine = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) {
        eventType = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLine = line.slice(5).trim();
      }
    }
    if (!dataLine) {
      continue;
    }
    try {
      const data = JSON.parse(dataLine) as Record<string, unknown>;
      if (
        eventType === "progress" ||
        eventType === "answer_token" ||
        eventType === "citation" ||
        eventType === "done" ||
        eventType === "error"
      ) {
        events.push({ type: eventType, data: data as never });
      }
    } catch {
      // skip malformed payloads
    }
  }

  return { events, remainder };
}
