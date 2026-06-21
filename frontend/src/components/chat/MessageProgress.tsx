import { type FC, useEffect, useRef, useState } from "react";

import type { TurnProgress } from "@/lib/progress";
import type { ProgressView } from "@/lib/chatPreferences";
import {
  aggregateProgressDisplay,
  formatElapsedSeconds,
  type DisplayProgressStep,
} from "@/lib/progressDisplay";
import { cn } from "@/lib/utils";

type MessageProgressProps = {
  progress: TurnProgress;
  view: ProgressView;
};

function ProgressStepDot({ status }: { status: DisplayProgressStep["status"] }) {
  return (
    <span
      className={cn(
        "progress-step-dot size-[7px] shrink-0 rounded-full",
        status === "pending" && "bg-border",
        status === "completed" && "bg-brand-accent",
        status === "running" && "progress-step-dot--running bg-primary",
        status === "failed" && "bg-destructive",
      )}
      aria-hidden
    />
  );
}

function ProgressStepRow({
  step,
  showDetails,
}: {
  step: DisplayProgressStep;
  showDetails: boolean;
}) {
  return (
    <li
      className={cn(
        "flex items-center gap-2 py-[0.22rem] text-[0.78em] transition-colors",
        step.status === "pending" && "text-muted-foreground",
        step.status === "completed" && "text-foreground",
        step.status === "running" && "text-primary font-medium",
        step.status === "failed" && "text-destructive",
      )}
    >
      <ProgressStepDot status={step.status} />
      <span className="min-w-0 flex-1">{step.label}</span>
      {showDetails && step.detailHint ? (
        <span className="text-faint ms-auto shrink-0 font-mono text-[0.66em]">
          {step.detailHint}
        </span>
      ) : null}
    </li>
  );
}

export const MessageProgress: FC<MessageProgressProps> = ({ progress, view }) => {
  const display = aggregateProgressDisplay(progress);
  const isActive = progress.status === "running";
  const showDetails = view === "detailed";
  const startedAtRef = useRef<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!isActive) {
      return;
    }

    if (startedAtRef.current == null) {
      startedAtRef.current = Date.now();
    }

    const startedAt = startedAtRef.current;

    const tick = () => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    };

    tick();
    const intervalId = window.setInterval(tick, 1000);
    return () => window.clearInterval(intervalId);
  }, [isActive]);

  if (progress.steps.length === 0) {
    return null;
  }

  return (
    <div
      className="border-border bg-card mb-3 overflow-hidden rounded-xl border shadow-[var(--card-highlight)]"
      data-detailed={showDetails ? "true" : "false"}
      role="region"
      aria-label="Answer progress"
    >
      <div className="flex items-center gap-2.5 px-3.5 py-2.5">
        {isActive ? (
          <span
            className="border-border border-t-primary size-[15px] shrink-0 animate-spin rounded-full border-2"
            aria-hidden
          />
        ) : (
          <span className="size-[15px] shrink-0" aria-hidden />
        )}
        <span
          className={cn(
            "text-[0.82em] font-medium",
            isActive ? "text-foreground" : "text-muted-foreground",
          )}
        >
          {display.headerLabel}
        </span>
        {isActive ? (
          <span
            className="text-faint ms-auto text-[0.7em] tabular-nums"
            aria-live="polite"
            aria-atomic="true"
          >
            {formatElapsedSeconds(elapsedSeconds)}
          </span>
        ) : null}
      </div>

      <ol
        className="flex flex-col gap-px px-3.5 pb-3"
        aria-live="polite"
        aria-relevant="text"
      >
        {display.steps.map((step) => (
          <ProgressStepRow key={step.id} step={step} showDetails={showDetails} />
        ))}
      </ol>
    </div>
  );
};
