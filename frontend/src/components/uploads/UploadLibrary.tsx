import {
  Loader2Icon,
  Trash2Icon,
  UploadIcon,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type FC,
} from "react";

import { Button } from "@/components/ui/button";
import {
  deleteUpload,
  listUploads,
  uploadFile,
  type UserUpload,
} from "@/lib/api";
import {
  UPLOAD_PIPELINE_STAGES,
  pipelineProgressPercent,
  pipelineStageState,
} from "@/lib/uploadPipeline";
import { cn } from "@/lib/utils";

const ACCEPTED_TYPES =
  ".pdf,.docx,.md,.markdown,.png,.jpg,.jpeg,.webp";
const MAX_BYTES = 20 * 1024 * 1024;

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileTypeBadge(filename: string): string {
  const ext = filename.split(".").pop()?.toUpperCase() ?? "FILE";
  if (ext === "JPEG" || ext === "JPG" || ext === "PNG" || ext === "WEBP") {
    return "IMG";
  }
  if (ext === "MARKDOWN") {
    return "MD";
  }
  return ext.slice(0, 4);
}

function useCosmeticPipelinePhase(active: boolean): number {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (!active) {
      return;
    }
    const maxPhase = UPLOAD_PIPELINE_STAGES.length - 1;
    const id = window.setInterval(() => {
      setPhase((current) => Math.min(current + 1, maxPhase));
    }, 1500);
    return () => window.clearInterval(id);
  }, [active]);

  return phase;
}

type UploadPipelineProps = {
  indexed: boolean;
};

const UploadPipeline: FC<UploadPipelineProps> = ({ indexed }) => {
  const phase = useCosmeticPipelinePhase(!indexed);

  if (indexed) {
    return null;
  }

  const progress = pipelineProgressPercent(phase);

  return (
    <>
      <div className="upload-pipeline mt-2 flex flex-wrap items-center gap-[0.3rem]">
        {UPLOAD_PIPELINE_STAGES.map((label, index) => {
          const state = pipelineStageState(index, phase);
          return (
            <span
              key={label}
              className={cn(
                "upload-pchip",
                state === "done" && "upload-pchip--done",
                state === "running" && "upload-pchip--running",
              )}
            >
              {label}
            </span>
          );
        })}
      </div>
      <div className="upload-pbar mt-[0.55rem]" aria-hidden>
        <span
          className="upload-pbar-fill"
          style={{ width: `${progress}%` }}
        />
      </div>
    </>
  );
};

type UploadFileCardProps = {
  upload: UserUpload;
  onDelete: () => void;
};

const UploadFileCard: FC<UploadFileCardProps> = ({ upload, onDelete }) => {
  const ready = upload.indexed;

  return (
    <li className="upload-file-card flex items-center gap-3 rounded-xl border px-[0.95rem] py-[0.85rem] shadow-[var(--card-highlight)]">
      <div className="bg-primary-muted text-primary flex size-[38px] shrink-0 items-center justify-center rounded-[10px] text-[0.68em] font-bold">
        {fileTypeBadge(upload.original_filename)}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-[0.84em] font-medium">
          {upload.original_filename}
        </p>
        <p className="text-faint mt-[0.15rem] text-[0.7em]">
          {formatBytes(upload.size_bytes)}
          {ready ? " · ready" : " · uploaded"}
        </p>
        <UploadPipeline indexed={ready} />
      </div>

      {!ready ? (
        <span className="text-primary shrink-0 text-[0.72em] font-medium">
          Processing
        </span>
      ) : null}

      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="text-faint hover:text-destructive size-7 shrink-0"
        aria-label={`Delete ${upload.original_filename}`}
        onClick={onDelete}
      >
        <Trash2Icon className="size-3.5" />
      </Button>
    </li>
  );
};

type UploadDropzoneProps = {
  disabled: boolean;
  onFile: (file: File) => void;
};

const UploadDropzone: FC<UploadDropzoneProps> = ({ disabled, onFile }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFiles = (files: FileList | null) => {
    const file = files?.[0];
    if (file) {
      onFile(file);
    }
  };

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setDragOver(false);
    if (disabled) {
      return;
    }
    handleFiles(event.dataTransfer.files);
  };

  return (
    <>
      <button
        type="button"
        className={cn(
          "upload-dropzone mb-[1.2rem] flex w-full items-center gap-[0.9rem] rounded-[14px] border-[1.5px] border-dashed px-[1.3rem] py-[1.3rem] text-left transition-colors duration-[var(--duration-normal)] ease-[var(--ease-default)] disabled:cursor-not-allowed disabled:opacity-60",
          dragOver
            ? "border-primary bg-primary-muted"
            : "border-border bg-card hover:border-primary hover:bg-primary-muted",
        )}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) {
            setDragOver(true);
          }
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <span className="bg-primary-muted text-primary grid size-10 shrink-0 place-items-center rounded-[11px]">
          <UploadIcon className="size-5" strokeWidth={1.7} />
        </span>
        <span>
          <span className="block text-[0.86em] font-medium">
            Drop a file or click to upload
          </span>
          <span className="text-muted-foreground block text-[0.74em]">
            PDF, DOCX, Markdown, or images (OCR) · up to 20 MB
          </span>
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept={ACCEPTED_TYPES}
        onChange={(event) => {
          handleFiles(event.target.files);
          event.target.value = "";
        }}
      />
    </>
  );
};

type UploadLibraryProps = {
  className?: string;
};

export const UploadLibrary: FC<UploadLibraryProps> = ({ className }) => {
  const [uploads, setUploads] = useState<UserUpload[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
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
    let cancelled = false;
    void (async () => {
      setError(null);
      try {
        const rows = await listUploads();
        if (!cancelled) {
          setUploads(rows.filter((row) => row.deleted_at == null));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load uploads");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasProcessing = uploads.some((upload) => !upload.indexed);

  useEffect(() => {
    if (!hasProcessing) {
      return;
    }
    const id = window.setInterval(() => {
      void refresh();
    }, 4000);
    return () => window.clearInterval(id);
  }, [hasProcessing, refresh]);

  const handleUpload = async (file: File) => {
    if (file.size > MAX_BYTES) {
      setError("File must be 20 MB or smaller.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await uploadFile(file);
      await refresh();
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
    <div className={cn("flex flex-col", className)}>
      <UploadDropzone disabled={uploading} onFile={(file) => void handleUpload(file)} />

      {uploading ? (
        <p className="text-muted-foreground mb-3 flex items-center gap-2 text-[0.78em]">
          <Loader2Icon className="size-3.5 animate-spin" />
          Uploading…
        </p>
      ) : null}

      {error ? (
        <p className="text-destructive mb-3 text-[0.78em]">{error}</p>
      ) : null}

      {loading ? (
        <p className="text-muted-foreground text-[0.78em]">Loading library…</p>
      ) : uploads.length === 0 ? (
        <p className="text-muted-foreground text-[0.78em]">
          No documents yet. Upload a file to add it to your library.
        </p>
      ) : (
        <ul className="flex flex-col gap-[0.7rem]">
          {uploads.map((upload) => (
            <UploadFileCard
              key={upload.id}
              upload={upload}
              onDelete={() => void handleDelete(upload.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
};
