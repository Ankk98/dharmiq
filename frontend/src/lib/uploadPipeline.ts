export const UPLOAD_PIPELINE_STAGES = [
  "Uploaded",
  "Parsed",
  "Chunking",
  "Embedding",
] as const;

export type UploadPipelineStage = (typeof UPLOAD_PIPELINE_STAGES)[number];

/** Cosmetic progress bar width per animation phase (demo uploadPipeline). */
const PHASE_PROGRESS = [25, 60, 100, 10] as const;

export function pipelineProgressPercent(phase: number): number {
  return PHASE_PROGRESS[phase % PHASE_PROGRESS.length] ?? 25;
}

export function pipelineStageState(
  stageIndex: number,
  phase: number,
): "done" | "running" | "pending" {
  const active = phase % UPLOAD_PIPELINE_STAGES.length;
  if (stageIndex < active) {
    return "done";
  }
  if (stageIndex === active) {
    return "running";
  }
  return "pending";
}
