import { createContext } from "react";

import type { UserUpload } from "@/lib/api";

export type SessionAttachmentsContextValue = {
  sessionId: string | null;
  attachedUploads: UserUpload[];
  attachedUploadIds: Set<string>;
  error: string | null;
  openPicker: () => void;
  attachUpload: (uploadId: string) => Promise<void>;
  handleDetach: (uploadId: string) => Promise<void>;
};

export const SessionAttachmentsContext =
  createContext<SessionAttachmentsContextValue | null>(null);
