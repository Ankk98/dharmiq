import { AlertCircleIcon } from "lucide-react";
import type { FC } from "react";

import { Button } from "@/components/ui/button";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";

type RefusalCardProps = {
  content: string;
};

function refusalBody(content: string): string {
  const trimmed = content.trim();
  if (!trimmed) {
    return "I couldn't find sufficient sources in the corpus or your attached documents to answer this with confidence.";
  }
  return trimmed;
}

export const RefusalCard: FC<RefusalCardProps> = ({ content }) => {
  const { openAttachPicker } = useChatRuntimeState();

  return (
    <div className="border-border bg-card rounded-xl border p-4 shadow-[var(--card-highlight)]">
      <div className="text-warning mb-1.5 flex items-center gap-2 text-[0.86em] font-semibold">
        <AlertCircleIcon className="size-4 shrink-0" aria-hidden />
        <span>I can&apos;t answer this reliably</span>
      </div>
      <p className="text-muted-foreground text-[0.82em] leading-relaxed">{refusalBody(content)}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="border-primary text-primary bg-primary-muted hover:bg-primary-muted/80 h-auto rounded-full px-3 py-1.5 text-[0.74em]"
          onClick={() => {
            document
              .querySelector<HTMLTextAreaElement>('[aria-label="Message input"]')
              ?.focus();
          }}
        >
          Rephrase question
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="border-primary text-primary bg-primary-muted hover:bg-primary-muted/80 h-auto rounded-full px-3 py-1.5 text-[0.74em]"
          onClick={() => openAttachPicker()}
        >
          Attach a document
        </Button>
      </div>
    </div>
  );
};
