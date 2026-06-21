import { cn } from "@/lib/utils";

type WordmarkProps = {
  compact?: boolean;
  className?: string;
};

export function Wordmark({ compact = false, className }: WordmarkProps) {
  return (
    <div className={cn("flex items-center gap-2 whitespace-nowrap", className)}>
      <span className="bg-primary text-primary-foreground shadow-[var(--glow)] flex size-7 shrink-0 items-center justify-center rounded-[9px] font-sans text-[0.78em] font-bold">
        D
      </span>
      {!compact ? (
        <span className="font-display text-[1.1em] font-semibold tracking-tight">
          Dhar<span className="text-primary not-italic">miq</span>
        </span>
      ) : null}
    </div>
  );
}
