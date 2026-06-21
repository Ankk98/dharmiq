import type { FC } from "react";

import { Button } from "@/components/ui/button";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";

type ClarifyCardProps = {
  reason?: string;
  questions: string[];
};

export const ClarifyCard: FC<ClarifyCardProps> = ({ reason, questions }) => {
  const { submitUserMessage, forceAnswer, isRunning } = useChatRuntimeState();

  const primaryQuestion = questions[0] ?? "Could you share a bit more detail?";

  return (
    <div className="border-border bg-raised rounded-[5px_14px_14px_14px] border p-4 shadow-[var(--card-highlight)]">
      {reason ? (
        <p className="text-faint mb-2 text-[0.68em]">{reason}</p>
      ) : (
        <p className="text-faint mb-2 text-[0.68em]">
          This helps me pick the right Act and state rules
        </p>
      )}
      <p className="text-foreground mb-3 text-[0.9em] leading-relaxed">{primaryQuestion}</p>
      <div className="flex flex-wrap items-center gap-2">
        {questions.map((question) => (
          <Button
            key={question}
            type="button"
            variant="outline"
            size="sm"
            className="bg-card hover:border-primary hover:text-primary h-auto rounded-full px-3 py-1.5 text-[0.76em] font-normal"
            disabled={isRunning}
            onClick={() => void submitUserMessage(question)}
          >
            {question}
          </Button>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="text-muted-foreground ms-auto h-auto rounded-full border-dashed px-3 py-1.5 text-[0.76em] font-normal"
          disabled={isRunning}
          onClick={() => void forceAnswer()}
        >
          Answer with what you have
        </Button>
      </div>
    </div>
  );
};
