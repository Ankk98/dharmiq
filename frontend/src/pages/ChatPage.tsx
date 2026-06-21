import { Thread } from "@/components/assistant-ui/thread";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";

export function ChatPage() {
  const { slowNotice, isRunning, streamError } = useChatRuntimeState();

  return (
    <>
      {slowNotice && isRunning ? (
        <div className="bg-muted/50 border-border border-b px-4 py-2 text-sm">
          This answer is taking longer than usual. Please wait; we&apos;re still
          working on it.
        </div>
      ) : null}
      {streamError ? (
        <div className="bg-destructive/10 text-destructive border-border border-b px-4 py-2 text-sm">
          {streamError}
        </div>
      ) : null}
      <div className="min-h-0 flex-1">
        <Thread />
      </div>
    </>
  );
}
