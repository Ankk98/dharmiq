export type ProgressView = "concise" | "detailed";

const PROGRESS_VIEW_KEY = "dharmiq_progress_view";

export function getProgressView(): ProgressView {
  const stored = localStorage.getItem(PROGRESS_VIEW_KEY);
  return stored === "detailed" ? "detailed" : "concise";
}

export function setProgressView(view: ProgressView): void {
  localStorage.setItem(PROGRESS_VIEW_KEY, view);
}
