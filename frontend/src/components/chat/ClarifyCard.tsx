import { useState, type FC, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import type { ClarifierItem } from "@/lib/clarifier";
import { cn } from "@/lib/utils";

type ClarifyCardProps = {
  reason?: string;
  items: ClarifierItem[];
  interactive?: boolean;
};

export const ClarifyCard: FC<ClarifyCardProps> = ({
  reason,
  items,
  interactive = false,
}) => {
  const { submitUserMessage, forceAnswer, isRunning } = useChatRuntimeState();
  const [customAnswer, setCustomAnswer] = useState("");

  const submitCustom = (event?: FormEvent) => {
    event?.preventDefault();
    const text = customAnswer.trim();
    if (!text || isRunning) {
      return;
    }
    setCustomAnswer("");
    void submitUserMessage(text);
  };

  return (
    <div
      className={cn(
        "border-border bg-raised w-full max-w-[min(72ch,100%)] rounded-[5px_14px_14px_14px] border p-4 shadow-[var(--card-highlight)]",
        !interactive && "opacity-95",
      )}
    >
      {reason ? (
        <p className="text-faint mb-3 text-[0.68em] leading-relaxed">{reason}</p>
      ) : (
        <p className="text-faint mb-3 text-[0.68em]">
          This helps me pick the right Act and state rules
        </p>
      )}

      <div className="flex flex-col gap-4">
        {items.map((item, index) => (
          <div key={`${item.question}-${index}`} className="min-w-0">
            <p className="text-foreground text-[0.9em] leading-relaxed wrap-break-word">
              {items.length > 1 ? `${index + 1}. ` : null}
              {item.question}
            </p>
            {item.why ? (
              <p className="text-faint mt-1 text-[0.72em] leading-relaxed wrap-break-word">
                {item.why}
              </p>
            ) : null}

            {interactive && item.options.length > 0 ? (
              <div className="mt-2.5 flex flex-wrap gap-2">
                {item.options.map((option) => (
                  <Button
                    key={option}
                    type="button"
                    variant="outline"
                    size="sm"
                    className="bg-card hover:border-primary hover:text-primary h-auto max-w-full rounded-full px-3 py-1.5 text-[0.76em] font-normal whitespace-normal"
                    disabled={isRunning}
                    onClick={() => void submitUserMessage(option)}
                  >
                    <span className="wrap-break-word text-start">{option}</span>
                  </Button>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {interactive ? (
        <div className="border-border mt-4 flex flex-col gap-2 border-t pt-3">
          <form className="flex flex-col gap-2 sm:flex-row" onSubmit={submitCustom}>
            <Input
              value={customAnswer}
              onChange={(event) => setCustomAnswer(event.target.value)}
              placeholder="Something else — type your answer"
              className="border-border bg-background h-10 flex-1 rounded-[10px] text-[0.82em]"
              disabled={isRunning}
              aria-label="Custom answer"
            />
            <Button
              type="submit"
              size="sm"
              className="h-10 shrink-0 rounded-[10px] px-4 text-[0.82em]"
              disabled={isRunning || customAnswer.trim().length === 0}
            >
              Send
            </Button>
          </form>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="text-muted-foreground h-auto self-end rounded-full border-dashed px-3 py-1.5 text-[0.76em] font-normal"
            disabled={isRunning}
            onClick={() => void forceAnswer()}
          >
            Answer with what you have
          </Button>
        </div>
      ) : null}
    </div>
  );
};
