import { ChevronDownIcon, ChevronUpIcon, Loader2Icon, WorkflowIcon } from "lucide-react";
import { type FC, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { ProgressStep, TurnProgress } from "@/lib/progress";
import type { ProgressView } from "@/lib/chatPreferences";
import { cn } from "@/lib/utils";

type MessageProgressProps = {
  progress: TurnProgress;
  view: ProgressView;
  onViewChange?: (view: ProgressView) => void;
  defaultOpen?: boolean;
};

function StepIcon({ status }: { status: ProgressStep["status"] }) {
  if (status === "running") {
    return <Loader2Icon className="text-primary size-4 animate-spin" aria-hidden />;
  }
  if (status === "failed") {
    return (
      <span className="bg-destructive size-2 rounded-full" aria-label="Failed" />
    );
  }
  return <span className="bg-primary size-2 rounded-full" aria-label="Completed" />;
}

export const MessageProgress: FC<MessageProgressProps> = ({
  progress,
  view,
  onViewChange,
  defaultOpen = false,
}) => {
  const [open, setOpen] = useState(defaultOpen || progress.status === "running");
  const showDetails = view === "detailed";
  const isActive = progress.status === "running";
  const completedCount = progress.steps.filter((step) => step.status === "completed").length;

  if (progress.steps.length === 0) {
    return null;
  }

  const summaryLabel = isActive
    ? "Working on your question…"
    : `Processed ${completedCount} step${completedCount === 1 ? "" : "s"}`;

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="border-border bg-muted/30 mb-3 rounded-lg border"
    >
      <div className="px-3 py-2">
        <CollapsibleTrigger className="text-muted-foreground hover:text-foreground flex w-full items-center gap-2 text-left text-sm transition-colors">
          <WorkflowIcon className="size-4 shrink-0" aria-hidden />
          <span className={cn(isActive && "text-foreground font-medium")}>{summaryLabel}</span>
          <ChevronDownIcon
            className={cn(
              "ms-auto size-4 shrink-0 transition-transform",
              open ? "rotate-180" : "rotate-0",
            )}
          />
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent className="border-border border-t px-3 py-2">
        {onViewChange ? (
          <div className="mb-2 flex justify-end">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-muted-foreground h-7 gap-1 px-2 text-xs"
              onClick={() => onViewChange(showDetails ? "concise" : "detailed")}
            >
              {showDetails ? (
                <>
                  Hide details
                  <ChevronUpIcon className="size-3.5" />
                </>
              ) : (
                <>
                  Show details
                  <ChevronDownIcon className="size-3.5" />
                </>
              )}
            </Button>
          </div>
        ) : null}
        <ol className="flex flex-col gap-2">
          {progress.steps.map((step) => (
            <li
              key={step.stepId}
              className={cn(
                "flex items-start gap-2 text-sm transition-opacity",
                step.status === "completed" && "opacity-80",
              )}
            >
              <span className="mt-1.5 flex size-4 shrink-0 items-center justify-center">
                <StepIcon status={step.status} />
              </span>
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    step.status === "running" && "text-foreground font-medium",
                    step.status === "failed" && "text-destructive",
                  )}
                >
                  {step.label}
                </p>
                {showDetails && step.status === "completed" ? (
                  <div className="text-muted-foreground mt-0.5 space-y-1 text-xs">
                    {step.agent ? <p>Agent: {step.agent}</p> : null}
                    {step.chunkCount != null ? (
                      <p>Retrieved {step.chunkCount} source chunk(s)</p>
                    ) : null}
                    {step.preview && step.preview.length > 0 ? (
                      <ul className="list-disc ps-4">
                        {step.preview.map((item) => (
                          <li key={item} className="truncate">
                            {item}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
};
