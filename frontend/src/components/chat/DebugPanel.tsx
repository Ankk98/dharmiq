import { useState, type FC } from "react";

import type { DebugEvent } from "@/hooks/useChatStream";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type DebugPanelProps = {
  events: DebugEvent[];
  visible: boolean;
};

export const DebugPanel: FC<DebugPanelProps> = ({ events, visible }) => {
  const [open, setOpen] = useState(false);

  if (!visible) {
    return null;
  }

  return (
    <div className="border-border border-b">
      <div className="flex items-center justify-between px-4 py-2">
        <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
          Debug
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Hide" : "Show"} ({events.length})
        </Button>
      </div>
      {open ? (
        <div className="max-h-48 overflow-y-auto px-4 pb-3">
          {events.length === 0 ? (
            <p className="text-muted-foreground text-xs">No debug events yet.</p>
          ) : (
            <ul className="space-y-2">
              {events.map((event) => (
                <li
                  key={event.seq}
                  className={cn(
                    "bg-muted/50 rounded-md border p-2 font-mono text-xs",
                  )}
                >
                  <p className="text-muted-foreground mb-1">
                    seq {event.seq} · {event.step_id ?? event.label}
                  </p>
                  <pre className="whitespace-pre-wrap break-all">
                    {JSON.stringify(
                      {
                        rerank_scores: event.rerank_scores,
                        queries: event.queries,
                        validator_issues: event.validator_issues,
                        chunk_snippets: event.chunk_snippets,
                        token_breakdown: event.token_breakdown,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
};
