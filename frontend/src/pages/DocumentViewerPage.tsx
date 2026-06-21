import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { documentFileUrl, getToken } from "@/lib/api";

export function DocumentViewerPage() {
  const [params] = useSearchParams();
  const documentId = window.location.pathname.split("/").pop() ?? "";
  const sourceType = (params.get("source_type") ?? "corpus") as "corpus" | "upload";
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [title, setTitle] = useState("Document");
  const [error, setError] = useState<string | null>(() =>
    !getToken() || !documentId ? "Unable to load document." : null,
  );

  useEffect(() => {
    const token = getToken();
    if (!token || !documentId) {
      return;
    }

    let active = true;
    let blobUrl: string | null = null;

    void (async () => {
      try {
        const metaResponse = await fetch(
          `/api/docs/${documentId}?source_type=${sourceType}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (!metaResponse.ok) {
          throw new Error("Document not found");
        }
        const meta = (await metaResponse.json()) as { title: string; mime_type: string };
        if (!active) {
          return;
        }
        setTitle(meta.title);

        const fileResponse = await fetch(documentFileUrl(documentId, sourceType), {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!fileResponse.ok) {
          throw new Error("Document file unavailable");
        }
        const blob = await fileResponse.blob();
        blobUrl = URL.createObjectURL(blob);
        if (active) {
          setObjectUrl(blobUrl);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load document");
        }
      }
    })();

    return () => {
      active = false;
      if (blobUrl) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [documentId, sourceType]);

  return (
    <div className="flex h-full flex-col">
      <header className="border-border flex items-center justify-between border-b px-4 py-3">
        <div>
          <p className="text-sm font-medium">{title}</p>
          <p className="text-muted-foreground text-xs">Source: {sourceType}</p>
        </div>
        <Link to="/">
          <Button variant="outline" size="sm">
            Back to chat
          </Button>
        </Link>
      </header>
      <div className="flex-1 overflow-hidden">
        {error ? <p className="text-destructive p-4 text-sm">{error}</p> : null}
        {!error && !objectUrl ? (
          <p className="text-muted-foreground p-4 text-sm">Loading document...</p>
        ) : null}
        {objectUrl ? (
          <iframe title={title} src={objectUrl} className="h-full w-full border-0" />
        ) : null}
      </div>
    </div>
  );
}
