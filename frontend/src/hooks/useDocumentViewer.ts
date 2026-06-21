import { useEffect, useState } from "react";

import { documentFileUrl, getToken } from "@/lib/api";

type UseDocumentViewerOptions = {
  documentId: string;
  sourceType: "corpus" | "upload";
};

type DocumentViewerState = {
  title: string;
  objectUrl: string | null;
  error: string | null;
  isLoading: boolean;
};

export function useDocumentViewer({
  documentId,
  sourceType,
}: UseDocumentViewerOptions): DocumentViewerState {
  const [title, setTitle] = useState("Document");
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token || !documentId) {
      return;
    }

    let active = true;
    let blobUrl: string | null = null;

    void (async () => {
      setIsLoading(true);
      setError(null);
      setObjectUrl(null);
      setTitle("Document");

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
      } finally {
        if (active) {
          setIsLoading(false);
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

  return { title, objectUrl, error, isLoading };
}
