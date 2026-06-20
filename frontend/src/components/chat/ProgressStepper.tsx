import { ChevronDownIcon, ChevronUpIcon, Loader2Icon } from "lucide-react";
import type { FC } from "react";

import type { ProgressStep } from "@/hooks/useChatStream";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ProgressView } from "@/lib/chatPreferences";

type ProgressStepperProps = {
  steps: ProgressStep[];
  isActive: boolean;
  view: ProgressView;
  onViewChange: (view: ProgressView) => void;
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

export const ProgressStepper: FC<ProgressStepperProps> = ({
  steps,
  isActive,
  view,
  onViewChange,
}) => {
  if (!isActive && steps.length === 0) {
    return null;
  }

  const showDetails = view === "detailed";

  return (
    <div className="border-border bg-muted/30 border-b px-4 py-3">
      <div className="mx-auto flex w-full max-w-[44rem] flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">
            {isActive ? "Working on your question…" : "Progress"}
          </p>
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

        <ol className="flex flex-col gap-2">
          {steps.map((step) => (
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
      </div>
    </div>
  );
};
