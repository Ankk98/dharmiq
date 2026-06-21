import { cn } from "@/lib/utils";

type LogoMarkProps = {
  className?: string;
  size?: number;
};

/** Dharmachakra mark from dharmiq.in, recolored with Ashoka design tokens. */
export function LogoMark({ className, size = 28 }: LogoMarkProps) {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("shrink-0 text-primary", className)}
      aria-hidden
    >
      <g stroke="currentColor" strokeWidth="2.5" fill="none">
        <path
          d="M50 5 L55 15 L50 25 L45 15 Z"
          className="fill-brand-accent"
          fillOpacity={0.85}
          stroke="none"
        />
        <path
          d="M95 50 L85 45 L75 50 L85 55 Z"
          className="fill-brand-accent"
          fillOpacity={0.85}
          stroke="none"
        />
        <path
          d="M50 95 L45 85 L50 75 L55 85 Z"
          className="fill-brand-accent"
          fillOpacity={0.85}
          stroke="none"
        />
        <path
          d="M5 50 L15 55 L25 50 L15 45 Z"
          className="fill-brand-accent"
          fillOpacity={0.85}
          stroke="none"
        />

        <path
          d="M78.5 21.5 L71.5 28.5 L64.5 21.5 L71.5 14.5 Z"
          className="fill-brand-accent"
          fillOpacity={0.55}
          stroke="none"
        />
        <path
          d="M78.5 78.5 L71.5 71.5 L78.5 64.5 L85.5 71.5 Z"
          className="fill-brand-accent"
          fillOpacity={0.55}
          stroke="none"
        />
        <path
          d="M21.5 78.5 L28.5 71.5 L35.5 78.5 L28.5 85.5 Z"
          className="fill-brand-accent"
          fillOpacity={0.55}
          stroke="none"
        />
        <path
          d="M21.5 21.5 L28.5 28.5 L21.5 35.5 L14.5 28.5 Z"
          className="fill-brand-accent"
          fillOpacity={0.55}
          stroke="none"
        />

        <circle cx="50" cy="50" r="38" strokeWidth="3" />
        <circle cx="50" cy="50" r="33" strokeWidth="1.5" />
        <circle cx="50" cy="50" r="25" strokeWidth="2" />

        <line x1="50" y1="25" x2="50" y2="75" strokeWidth="2" />
        <line x1="25" y1="50" x2="75" y2="50" strokeWidth="2" />
        <line x1="32.32" y1="32.32" x2="67.68" y2="67.68" strokeWidth="2" />
        <line x1="67.68" y1="32.32" x2="32.32" y2="67.68" strokeWidth="2" />

        <circle
          cx="50"
          cy="50"
          r="6"
          className="fill-brand-accent"
          stroke="none"
        />
        <circle
          cx="50"
          cy="50"
          r="3"
          className="fill-background"
          stroke="none"
        />
      </g>
    </svg>
  );
}
