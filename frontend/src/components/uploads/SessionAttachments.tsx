import { PaperclipIcon, XIcon } from "lucide-react";
import {
  useCallback,
  useContext,
  useEffect,
  useState,
  type FC,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import { useToast } from "@/hooks/useToast";
import {
  attachUploads,
  detachUpload,
  listSessionAttachments,
  listUploads,
  type SessionAttachment,
  type UserUpload,
} from "@/lib/api";
import {
  SessionAttachmentsContext,
  type SessionAttachmentsContextValue,
} from "@/providers/session-attachments-context";
import { cn } from "@/lib/utils";

function notifyAttached(toast: (options: { title: string; detail?: string }) => void, filenames: string[]) {
  if (filenames.length === 0) {
    return;
  }
  if (filenames.length === 1) {
    toast({ title: "Document attached", detail: filenames[0] });
    return;
  }
  toast({
    title: `${filenames.length} documents attached`,
    detail: filenames.join(", "),
  });
}

type AttachmentChipProps = {
  filename: string;
  onDetach: () => void;
};

const AttachmentChip: FC<AttachmentChipProps> = ({ filename, onDetach }) => (
  <span className="composer-attach-chip border-border bg-card text-foreground inline-flex items-center gap-[0.45rem] rounded-full border px-[0.6rem] py-[0.35rem] text-[0.74em] shadow-[var(--card-highlight)]">
    <span className="bg-brand-accent size-1.5 shrink-0 rounded-full" aria-hidden />
    <span className="max-w-36 truncate">{filename}</span>
    <button
      type="button"
      className="text-faint hover:text-destructive cursor-pointer leading-none transition-colors"
      aria-label={`Remove ${filename}`}
      onClick={onDetach}
    >
      ✕
    </button>
  </span>
);

function useSessionAttachmentsContext(): SessionAttachmentsContextValue {
  const context = useContext(SessionAttachmentsContext);
  if (!context) {
    throw new Error("SessionAttachments components must be used within SessionAttachmentsProvider");
  }
  return context;
}

type SessionAttachmentsProviderProps = {
  sessionId: string | null;
  children: ReactNode;
};

export const SessionAttachmentsProvider: FC<SessionAttachmentsProviderProps> = ({
  sessionId,
  children,
}) => {
  const { registerAttachPicker, refreshMessages } = useChatRuntimeState();
  const { toast } = useToast();
  const [attachments, setAttachments] = useState<SessionAttachment[]>([]);
  const [uploadsById, setUploadsById] = useState<Map<string, UserUpload>>(new Map());
  const [pickerOpen, setPickerOpen] = useState(false);
  const [library, setLibrary] = useState<UserUpload[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!sessionId) {
      setAttachments([]);
      return;
    }
    setError(null);
    try {
      const [attached, uploads] = await Promise.all([
        listSessionAttachments(sessionId),
        listUploads(),
      ]);
      setAttachments(attached);
      const map = new Map<string, UserUpload>();
      for (const upload of uploads) {
        if (upload.deleted_at == null) {
          map.set(upload.id, upload);
        }
      }
      setUploadsById(map);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load attachments");
    }
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!sessionId) {
        if (!cancelled) {
          setAttachments([]);
          setUploadsById(new Map());
        }
        return;
      }

      setError(null);
      try {
        const [attached, uploads] = await Promise.all([
          listSessionAttachments(sessionId),
          listUploads(),
        ]);
        if (cancelled) {
          return;
        }
        setAttachments(attached);
        const map = new Map<string, UserUpload>();
        for (const upload of uploads) {
          if (upload.deleted_at == null) {
            map.set(upload.id, upload);
          }
        }
        setUploadsById(map);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load attachments");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const openPicker = useCallback(async () => {
    setPickerOpen(true);
    setSelected(new Set());
    setError(null);
    try {
      const uploads = await listUploads();
      setLibrary(uploads.filter((row) => row.deleted_at == null && row.indexed));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load library");
    }
  }, []);

  useEffect(() => {
    registerAttachPicker(openPicker);
    return () => registerAttachPicker(null);
  }, [openPicker, registerAttachPicker]);

  const attachUpload = async (uploadId: string) => {
    if (!sessionId) {
      return;
    }
    setError(null);
    const upload = uploadsById.get(uploadId);
    try {
      await attachUploads(sessionId, [uploadId]);
      await refresh();
      await refreshMessages();
      if (upload) {
        notifyAttached(toast, [upload.original_filename]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attach failed");
    }
  };

  const confirmAttach = async () => {
    if (!sessionId || selected.size === 0) {
      return;
    }
    setError(null);
    const selectedIds = Array.from(selected);
    const attachedNames = selectedIds
      .map((id) => library.find((upload) => upload.id === id)?.original_filename)
      .filter((name): name is string => name != null);
    try {
      await attachUploads(sessionId, selectedIds);
      setPickerOpen(false);
      await refresh();
      await refreshMessages();
      notifyAttached(toast, attachedNames);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attach failed");
    }
  };

  const handleDetach = async (uploadId: string) => {
    if (!sessionId) {
      return;
    }
    setError(null);
    try {
      await detachUpload(sessionId, uploadId);
      await refresh();
      await refreshMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Detach failed");
    }
  };

  const attachedUploadIds = new Set(attachments.map((attachment) => attachment.upload_id));
  const attachedUploads = attachments
    .map((attachment) => uploadsById.get(attachment.upload_id))
    .filter((upload): upload is UserUpload => upload != null);

  return (
    <SessionAttachmentsContext.Provider
      value={{
        sessionId,
        attachedUploads,
        attachedUploadIds,
        error,
        openPicker,
        attachUpload,
        handleDetach,
      }}
    >
      {children}
      {pickerOpen ? (
        <div className="bg-background fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="bg-background border-border w-full max-w-md rounded-lg border p-4 shadow-lg"
            role="dialog"
            aria-labelledby="attach-dialog-title"
          >
            <h2 id="attach-dialog-title" className="mb-3 text-sm font-semibold">
              Attach documents to this chat
            </h2>
            {library.length === 0 ? (
              <p className="text-muted-foreground mb-4 text-sm">
                No ready documents in your library. Upload a file first.
              </p>
            ) : (
              <ul className="mb-4 max-h-56 space-y-1 overflow-y-auto">
                {library.map((upload) => {
                  const isSelected = selected.has(upload.id);
                  const alreadyAttached = attachments.some(
                    (item) => item.upload_id === upload.id,
                  );
                  return (
                    <li key={upload.id}>
                      <label
                        className={cn(
                          "flex cursor-pointer items-center gap-2 rounded-md border px-2 py-1.5 text-sm",
                          isSelected && "border-primary bg-primary/5",
                          alreadyAttached && "opacity-50",
                        )}
                      >
                        <input
                          type="checkbox"
                          className="size-3.5"
                          checked={isSelected || alreadyAttached}
                          disabled={alreadyAttached}
                          onChange={() => {
                            setSelected((prev) => {
                              const next = new Set(prev);
                              if (next.has(upload.id)) {
                                next.delete(upload.id);
                              } else {
                                next.add(upload.id);
                              }
                              return next;
                            });
                          }}
                        />
                        <span className="truncate">{upload.original_filename}</span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setPickerOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={selected.size === 0}
                onClick={() => void confirmAttach()}
              >
                Attach selected
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </SessionAttachmentsContext.Provider>
  );
};

type SessionAttachmentsPanelProps = {
  className?: string;
};

export const SessionAttachmentsPanel: FC<SessionAttachmentsPanelProps> = ({ className }) => {
  const { sessionId, attachedUploads, error, openPicker, handleDetach } =
    useSessionAttachmentsContext();

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
          Attached to chat
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1 text-xs"
          disabled={!sessionId}
          onClick={() => void openPicker()}
        >
          <PaperclipIcon className="size-3.5" />
          Attach
        </Button>
      </div>

      {error ? <p className="text-destructive text-xs">{error}</p> : null}

      {attachedUploads.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          No documents attached. Uploads in your library are not searched until attached.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {attachedUploads.map((upload) => (
            <span
              key={upload.id}
              className="bg-primary/10 text-primary inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
            >
              <PaperclipIcon className="size-3" />
              <span className="max-w-36 truncate">{upload.original_filename}</span>
              <button
                type="button"
                className="hover:text-destructive rounded-full p-0.5"
                aria-label={`Remove ${upload.original_filename}`}
                onClick={() => void handleDetach(upload.id)}
              >
                <XIcon className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
};

/** Attachment chips rendered above the chat composer (demo `.attach` row). */
export const ComposerAttachmentChips: FC = () => {
  const { sessionId, attachedUploads, openPicker, handleDetach } =
    useSessionAttachmentsContext();

  if (attachedUploads.length === 0 && !sessionId) {
    return null;
  }

  return (
    <div className="composer-attach-row flex w-full flex-wrap gap-[0.45rem]">
      {attachedUploads.map((upload) => (
        <AttachmentChip
          key={upload.id}
          filename={upload.original_filename}
          onDetach={() => void handleDetach(upload.id)}
        />
      ))}
      <button
        type="button"
        className="border-border bg-card text-muted-foreground hover:text-foreground hover:border-ring cursor-pointer rounded-lg border px-[0.7rem] py-[0.4rem] text-[0.72em] shadow-[var(--card-highlight)] transition-colors disabled:cursor-not-allowed disabled:opacity-40"
        disabled={!sessionId}
        onClick={() => void openPicker()}
      >
        + Attach document
      </button>
    </div>
  );
};

/** @deprecated Use SessionAttachmentsProvider + SessionAttachmentsPanel */
export const SessionAttachments: FC<{ sessionId: string | null; className?: string }> = ({
  sessionId,
  className,
}) => (
  <SessionAttachmentsProvider sessionId={sessionId}>
    <SessionAttachmentsPanel className={className} />
  </SessionAttachmentsProvider>
);
