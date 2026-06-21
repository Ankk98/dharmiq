import { UploadLibrary } from "@/components/uploads/UploadLibrary";
import { SessionAttachmentsProvider } from "@/components/uploads/SessionAttachments";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";

export function DocumentsPage() {
  const { sessionId } = useChatRuntimeState();

  return (
    <SessionAttachmentsProvider sessionId={sessionId}>
      <div className="flex-1 overflow-y-auto p-6 max-md:p-4">
        <h1 className="font-display mb-1 text-[1.25em] font-semibold">Documents</h1>
        <p className="text-muted-foreground mb-[1.1rem] text-[0.8em]">
          Upload to your library, then attach files to a chat for focused answers.
        </p>
        <UploadLibrary />
      </div>
    </SessionAttachmentsProvider>
  );
}
