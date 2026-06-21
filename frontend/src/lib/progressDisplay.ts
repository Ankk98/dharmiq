import type { ProgressStep, TurnProgress } from "@/lib/progress";

export type DisplayStepStatus = "pending" | "running" | "completed" | "failed";

export type DisplayProgressStep = {
  id: string;
  label: string;
  status: DisplayStepStatus;
  detailHint?: string;
};

export type DisplayProgress = {
  steps: DisplayProgressStep[];
  status: TurnProgress["status"];
  headerLabel: string;
};

const DISPLAY_STEP_DEFS = [
  {
    id: "understand",
    label: "Understanding your question",
    failedIds: ["input_guard", "clarifier"] as const,
  },
  {
    id: "search",
    label: "Searching the law",
    failedIds: ["query_rewriter", "retrieve"] as const,
  },
  {
    id: "rank",
    label: "Ranking the best sources",
    failedIds: ["retrieve"] as const,
  },
  {
    id: "check",
    label: "Checking the answer",
    failedIds: ["answerer", "citation_enricher", "validator", "refusal"] as const,
  },
  {
    id: "write",
    label: "Writing the answer",
    failedIds: ["finalizer"] as const,
  },
] as const;

function stepMap(steps: ProgressStep[]): Map<string, ProgressStep> {
  return new Map(steps.map((step) => [step.stepId, step]));
}

function isUnderstandComplete(backend: Map<string, ProgressStep>): boolean {
  const inputGuard = backend.get("input_guard");
  if (!inputGuard || inputGuard.status !== "completed") {
    return false;
  }
  const clarifier = backend.get("clarifier");
  if (clarifier && clarifier.status !== "completed") {
    return false;
  }
  return true;
}

function isSearchComplete(backend: Map<string, ProgressStep>): boolean {
  return backend.get("retrieve")?.status === "completed";
}

function isCheckComplete(backend: Map<string, ProgressStep>): boolean {
  const finalizer = backend.get("finalizer");
  if (finalizer) {
    return true;
  }
  if (backend.get("refusal")?.status === "completed") {
    return true;
  }
  return backend.get("validator")?.status === "completed";
}

function isWriteComplete(backend: Map<string, ProgressStep>): boolean {
  return backend.get("finalizer")?.status === "completed";
}

function resolveActiveIndex(backend: Map<string, ProgressStep>): number {
  if (!isUnderstandComplete(backend)) {
    return 0;
  }
  if (!isSearchComplete(backend)) {
    return 1;
  }
  if (!isCheckComplete(backend)) {
    return 3;
  }
  if (!isWriteComplete(backend)) {
    return 4;
  }
  return 5;
}

function bucketFailed(
  backend: Map<string, ProgressStep>,
  ids: readonly string[],
): boolean {
  return ids.some((id) => backend.get(id)?.status === "failed");
}

function agentLabel(step: ProgressStep): string {
  return step.stepId.replace(/_/g, " ");
}

function topicFromPreview(preview: string[] | undefined): string | undefined {
  const first = preview?.[0];
  if (!first) {
    return undefined;
  }
  const title = first.split("—")[0]?.trim() ?? first;
  const words = title.split(/\s+/).filter(Boolean);
  const lastWord = words.at(-1);
  return lastWord?.replace(/[^\w]/g, "").toLowerCase() || undefined;
}

function formatUnderstandHint(backend: Map<string, ProgressStep>): string | undefined {
  const clarifier = backend.get("clarifier");
  const inputGuard = backend.get("input_guard");
  const step =
    clarifier?.status === "running" || clarifier?.status === "completed"
      ? clarifier
      : inputGuard;
  if (!step) {
    return undefined;
  }
  const agent = agentLabel(step);
  const topic = topicFromPreview(step.preview);
  return topic ? `${agent} · ${topic}` : agent;
}

function formatSearchHint(backend: Map<string, ProgressStep>): string | undefined {
  const retrieve = backend.get("retrieve");
  if (retrieve?.chunkCount != null) {
    return `corpus+uploads · ${retrieve.chunkCount} chunks`;
  }
  const queryRewriter = backend.get("query_rewriter");
  if (queryRewriter) {
    return agentLabel(queryRewriter);
  }
  return retrieve ? agentLabel(retrieve) : undefined;
}

function formatRankHint(backend: Map<string, ProgressStep>): string | undefined {
  const retrieve = backend.get("retrieve");
  if (!retrieve) {
    return undefined;
  }
  if (retrieve.chunkCount != null) {
    return `rerank · top ${retrieve.chunkCount}`;
  }
  return "rerank";
}

function formatCheckHint(backend: Map<string, ProgressStep>): string | undefined {
  const checkOrder = ["answerer", "citation_enricher", "validator", "refusal"] as const;
  for (let index = checkOrder.length - 1; index >= 0; index -= 1) {
    const step = backend.get(checkOrder[index]!);
    if (step?.status === "running") {
      return agentLabel(step);
    }
  }
  for (let index = checkOrder.length - 1; index >= 0; index -= 1) {
    const step = backend.get(checkOrder[index]!);
    if (step?.status === "completed") {
      return agentLabel(step);
    }
  }
  return undefined;
}

function buildDetailHint(
  defId: (typeof DISPLAY_STEP_DEFS)[number]["id"],
  backend: Map<string, ProgressStep>,
  status: DisplayStepStatus,
): string | undefined {
  if (status === "pending") {
    return undefined;
  }

  switch (defId) {
    case "understand":
      return formatUnderstandHint(backend);
    case "search":
      return formatSearchHint(backend);
    case "rank":
      return formatRankHint(backend);
    case "check":
      return formatCheckHint(backend);
    case "write":
      return "finalizer";
    default:
      return undefined;
  }
}

function resolveStepStatus(
  def: (typeof DISPLAY_STEP_DEFS)[number],
  index: number,
  activeIndex: number,
  backend: Map<string, ProgressStep>,
  turnStatus: TurnProgress["status"],
): DisplayStepStatus {
  if (turnStatus === "completed") {
    return "completed";
  }

  if (bucketFailed(backend, def.failedIds)) {
    return "failed";
  }

  if (def.id === "rank") {
    return isSearchComplete(backend) ? "completed" : "pending";
  }

  if (index < activeIndex) {
    return "completed";
  }

  if (index === activeIndex) {
    return "running";
  }

  return "pending";
}

export function aggregateProgressDisplay(progress: TurnProgress): DisplayProgress {
  const backend = stepMap(progress.steps);
  const activeIndex = resolveActiveIndex(backend);

  const steps = DISPLAY_STEP_DEFS.map((def, index) => {
    const status = resolveStepStatus(def, index, activeIndex, backend, progress.status);
    return {
      id: def.id,
      label: def.label,
      status,
      detailHint: buildDetailHint(def.id, backend, status),
    };
  });

  const headerLabel =
    progress.status === "running"
      ? "Working on your answer…"
      : progress.status === "failed"
        ? "Something went wrong"
        : "Answer ready";

  return {
    steps,
    status: progress.status,
    headerLabel,
  };
}

export function formatElapsedSeconds(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
