import { cn } from "@/lib/utils";

type DefaultAvatarProps = {
  className?: string;
};

/** Silhouette avatar from the design demo (§4.11) — no text initials. */
export function DefaultAvatar({ className }: DefaultAvatarProps) {
  return (
    <span
      className={cn(
        "border-border-subtle bg-primary-muted text-primary inline-flex size-[30px] shrink-0 items-center justify-center overflow-hidden rounded-full border shadow-[var(--card-highlight)]",
        className,
      )}
      aria-hidden
    >
      <svg viewBox="0 0 36 36" className="block size-full" aria-hidden>
        <circle
          className="fill-current opacity-[0.82]"
          cx="18"
          cy="13.4"
          r="5.6"
        />
        <path
          className="fill-current opacity-[0.82]"
          d="M7.6 30.8c0-5.5 4.7-9 10.4-9s10.4 3.5 10.4 9v.4H7.6z"
        />
        <path
          className="fill-primary-muted opacity-60"
          d="M18 21.6l-3 2.1 1.5 7.5h3l1.5-7.5z"
        />
      </svg>
    </span>
  );
}
