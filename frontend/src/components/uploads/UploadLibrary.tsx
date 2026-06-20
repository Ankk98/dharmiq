import { FileTextIcon, Loader2Icon, Trash2Icon, UploadIcon } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FC } from "react";

import { Button } from "@/components/ui/button";
import {
  deleteUpload,
  listUploads,
  uploadFile,
  type UserUpload,
} from "@/lib/api";
import { cn } from "@/lib/utils";

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

type UploadLibraryProps = {
  onUploadReady?: (upload: UserUpload) => void;
  className?: string;
};

export const UploadLibrary: FC<UploadLibraryProps> = ({ onUploadReady, className }) => {
  const [uploads, setUploads] = useState<UserUpload[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listUploads();
      setUploads(rows.filter((row) => row.deleted_at == null));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load uploads");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        const rows = await listUploads();
        setUploads(rows.filter((row) => row.deleted_at == null));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load uploads");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const created = await uploadFile(file);
      await refresh();
      onUploadReady?.(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (uploadId: string) => {
    setError(null);
    try {
      await deleteUpload(uploadId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-xs font-medium uppercase tracking-wide">
          Document library
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1 text-xs"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
        >
          {uploading ? (
            <Loader2Icon className="size-3.5 animate-spin" />
          ) : (
            <UploadIcon className="size-3.5" />
          )}
          Upload
        </Button>
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.md,.markdown,.png,.jpg,.jpeg,.webp"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              void handleUpload(file);
            }
            event.target.value = "";
          }}
        />
      </div>

      {error ? <p className="text-destructive text-xs">{error}</p> : null}

      {loading ? (
        <p className="text-muted-foreground text-xs">Loading library…</p>
      ) : uploads.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          Upload PDF, DOCX, or Markdown files to your library.
        </p>
      ) : (
        <ul className="flex max-h-40 flex-col gap-1 overflow-y-auto">
          {uploads.map((upload) => (
            <li
              key={upload.id}
              className="bg-muted/40 flex items-center gap-2 rounded-md border px-2 py-1.5 text-xs"
            >
              <FileTextIcon className="text-muted-foreground size-3.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{upload.original_filename}</p>
                <p className="text-muted-foreground">
                  {formatBytes(upload.size_bytes)}
                  {upload.indexed ? " · ready" : " · processing"}
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-6 shrink-0"
                aria-label={`Delete ${upload.original_filename}`}
                onClick={() => void handleDelete(upload.id)}
              >
                <Trash2Icon className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
