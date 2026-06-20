import type { StreamProgressPayload } from "@/lib/api";

export type ProgressStep = {
  stepId: string;
  label: string;
  status: "running" | "completed" | "failed";
  agent?: string;
  chunkCount?: number;
  preview?: string[];
};

export type TurnProgress = {
  steps: ProgressStep[];
  status: "running" | "completed" | "failed";
};

const STEP_ORDER = [
  "input_guard",
  "clarifier",
  "query_rewriter",
  "retrieve",
  "refusal",
  "answerer",
  "citation_enricher",
  "validator",
  "finalizer",
] as const;

export function isDebugProgressPayload(payload: StreamProgressPayload): boolean {
  return (
    payload.rerank_scores != null ||
    payload.queries != null ||
    payload.validator_issues != null ||
    payload.chunk_snippets != null ||
    payload.token_breakdown != null
  );
}

export function progressStepKey(payload: StreamProgressPayload): string {
  if (payload.step_id) {
    return payload.step_id;
  }
  return payload.label;
}

export function upsertProgressStep(
  steps: Map<string, ProgressStep>,
  order: string[],
  payload: StreamProgressPayload,
): void {
  const stepId = progressStepKey(payload);
  const existing = steps.get(stepId);
  if (!existing) {
    order.push(stepId);
  }
  steps.set(stepId, {
    stepId,
    label: payload.label,
    status: payload.status,
    agent: payload.agent ?? existing?.agent,
    chunkCount: payload.chunk_count ?? existing?.chunkCount,
    preview: payload.preview ?? existing?.preview,
  });
}

function sortStepOrder(order: string[]): string[] {
  const rank = new Map(STEP_ORDER.map((stepId, index) => [stepId, index]));
  return [...order].sort((left, right) => {
    const leftRank = rank.get(left as (typeof STEP_ORDER)[number]) ?? Number.MAX_SAFE_INTEGER;
    const rightRank = rank.get(right as (typeof STEP_ORDER)[number]) ?? Number.MAX_SAFE_INTEGER;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return order.indexOf(left) - order.indexOf(right);
  });
}

export function buildTurnProgress(payloads: StreamProgressPayload[]): TurnProgress {
  const steps = new Map<string, ProgressStep>();
  const order: string[] = [];

  for (const payload of payloads) {
    if (isDebugProgressPayload(payload)) {
      continue;
    }
    upsertProgressStep(steps, order, payload);
  }

  const sortedOrder = sortStepOrder(order);
  const stepList = sortedOrder
    .map((stepId) => steps.get(stepId))
    .filter((step): step is ProgressStep => step != null);

  const status: TurnProgress["status"] = stepList.some((step) => step.status === "running")
    ? "running"
    : stepList.some((step) => step.status === "failed")
      ? "failed"
      : "completed";

  return { steps: stepList, status };
}

export function applyProgressPayload(
  current: TurnProgress | undefined,
  payload: StreamProgressPayload,
): TurnProgress {
  const steps = new Map<string, ProgressStep>();
  const order: string[] = [];

  for (const step of current?.steps ?? []) {
    steps.set(step.stepId, step);
    order.push(step.stepId);
  }

  upsertProgressStep(steps, order, payload);

  const sortedOrder = sortStepOrder(order);
  const stepList = sortedOrder
    .map((stepId) => steps.get(stepId))
    .filter((step): step is ProgressStep => step != null);

  const status: TurnProgress["status"] = stepList.some((step) => step.status === "running")
    ? "running"
    : stepList.some((step) => step.status === "failed")
      ? "failed"
      : "completed";

  return { steps: stepList, status };
}

export function chatRequestIdFromMetadata(
  metadata: Record<string, unknown> | null | undefined,
): string | undefined {
  const value = metadata?.chat_request_id;
  return typeof value === "string" ? value : undefined;
}
