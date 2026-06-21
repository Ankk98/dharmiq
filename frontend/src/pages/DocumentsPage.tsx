import { UploadLibrary } from "@/components/uploads/UploadLibrary";

export function DocumentsPage() {
  return (
    <div className="flex-1 overflow-y-auto p-6 max-md:p-4">
      <h1 className="font-display mb-1 text-[1.25em] font-semibold">Documents</h1>
      <p className="text-muted-foreground mb-[1.1rem] text-[0.8em]">
        Upload and manage your personal document library. Attach files to a chat from the
        chat composer when you want focused answers.
      </p>
      <UploadLibrary />
    </div>
  );
}
