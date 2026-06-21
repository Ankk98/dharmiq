import { LogoMark } from "@/components/layout/LogoMark";
import { cn } from "@/lib/utils";

type WordmarkProps = {
  compact?: boolean;
  className?: string;
};

export function Wordmark({ compact = false, className }: WordmarkProps) {
  return (
    <div className={cn("flex items-center gap-2 whitespace-nowrap", className)}>
      <LogoMark size={compact ? 26 : 28} className="shadow-[var(--glow)]" />
      {!compact ? (
        <span className="font-display text-[1.1em] font-semibold tracking-tight">
          Dharm<span className="text-primary not-italic">iq</span>
        </span>
      ) : null}
    </div>
  );
}
