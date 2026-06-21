import type { ReactNode } from "react";

import { SessionAttachmentsProvider } from "@/components/uploads/SessionAttachments";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";

export function SessionAttachmentsShell({ children }: { children: ReactNode }) {
  const { sessionId } = useChatRuntimeState();

  return (
    <SessionAttachmentsProvider sessionId={sessionId}>
      {children}
    </SessionAttachmentsProvider>
  );
}
