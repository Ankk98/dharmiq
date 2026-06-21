import { useContext } from "react";

import {
  SessionAttachmentsContext,
  type SessionAttachmentsContextValue,
} from "@/providers/session-attachments-context";

export function useSessionAttachments(): SessionAttachmentsContextValue {
  const context = useContext(SessionAttachmentsContext);
  if (!context) {
    throw new Error(
      "useSessionAttachments must be used within SessionAttachmentsProvider",
    );
  }
  return context;
}
