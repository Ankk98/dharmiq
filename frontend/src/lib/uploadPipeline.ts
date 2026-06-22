export const UPLOAD_PIPELINE_STAGES = [
  "Uploaded",
  "Parsed",
  "Chunking",
  "Embedding",
] as const;

export type UploadPipelineStage = (typeof UPLOAD_PIPELINE_STAGES)[number];

export type ProcessingStage =
  | "uploaded"
  | "parsed"
  | "chunking"
  | "embedding"
  | "ready"
  | "failed";

const STAGE_INDEX: Record<ProcessingStage, number> = {
  uploaded: 0,
  parsed: 1,
  chunking: 2,
  embedding: 3,
  ready: UPLOAD_PIPELINE_STAGES.length,
  failed: -1,
};

const STAGE_PROGRESS = [25, 50, 75, 90] as const;

export function isTerminalStage(stage: ProcessingStage): boolean {
  return stage === "ready" || stage === "failed";
}

export function activePipelineIndex(stage: ProcessingStage): number {
  return STAGE_INDEX[stage];
}

export function pipelineProgressPercent(stage: ProcessingStage): number {
  if (stage === "ready") {
    return 100;
  }
  if (stage === "failed") {
    return 0;
  }
  const index = activePipelineIndex(stage);
  return STAGE_PROGRESS[index] ?? 25;
}

export function pipelineStageState(
  stageIndex: number,
  processingStage: ProcessingStage,
): "done" | "running" | "pending" | "failed" {
  if (processingStage === "failed") {
    if (stageIndex === UPLOAD_PIPELINE_STAGES.length - 1) {
      return "failed";
    }
    return "pending";
  }

  const active = activePipelineIndex(processingStage);
  if (stageIndex < active) {
    return "done";
  }
  if (stageIndex === active) {
    return "running";
  }
  return "pending";
}
