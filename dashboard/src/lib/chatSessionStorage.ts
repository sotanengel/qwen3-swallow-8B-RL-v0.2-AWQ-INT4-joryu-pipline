const ACTIVE_KEY = "joryu.chat.activeSessionId";

export function getActiveSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_KEY);
}

export function setActiveSessionId(id: string): void {
  window.localStorage.setItem(ACTIVE_KEY, id);
}

export function clearActiveSessionId(): void {
  window.localStorage.removeItem(ACTIVE_KEY);
}
