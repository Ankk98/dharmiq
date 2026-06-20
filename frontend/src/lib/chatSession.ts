const ACTIVE_SESSION_KEY = "dharmiq_active_session_id";

export function getStoredSessionId(): string | null {
  return localStorage.getItem(ACTIVE_SESSION_KEY);
}

export function setStoredSessionId(sessionId: string | null): void {
  if (sessionId) {
    localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
  } else {
    localStorage.removeItem(ACTIVE_SESSION_KEY);
  }
}
