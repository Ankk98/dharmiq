import type { FC, ReactNode } from "react";

type DisclaimerBlockProps = {
  children: ReactNode;
};

export const DisclaimerBlock: FC<DisclaimerBlockProps> = ({ children }) => (
  <div
    className="answer-disclaimer border-border bg-warning/8 my-3 flex items-start gap-2 rounded-e-[9px] border border-s-3 border-s-warning px-3.5 py-2.5"
    role="note"
  >
    <span className="text-warning shrink-0 text-sm font-bold" aria-hidden>
      i
    </span>
    <div className="text-muted-foreground text-[0.76em] leading-snug [&>p]:my-0">{children}</div>
  </div>
);
