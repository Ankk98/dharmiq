import { Thread } from "@/components/assistant-ui/thread";
import { ThreadList } from "@/components/assistant-ui/thread-list";
import { DebugPanel } from "@/components/chat/DebugPanel";
import { ProgressStepper } from "@/components/chat/ProgressStepper";
import { SessionAttachments } from "@/components/uploads/SessionAttachments";
import { UploadLibrary } from "@/components/uploads/UploadLibrary";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { ChatRuntimeProvider, useChatRuntimeState } from "@/providers/ChatRuntimeProvider";

function ChatLayout() {
  const { user, logout } = useAuth();
  const {
    slowNotice,
    isRunning,
    sessionId,
    progressView,
    setProgressView,
    progressSteps,
    streamStatus,
    debugEvents,
    streamError,
  } = useChatRuntimeState();

  const showProgress = isRunning || progressSteps.length > 0;

  return (
    <div className="flex h-full flex-col">
      <header className="border-border flex items-center justify-between border-b px-4 py-3">
        <div>
          <h1 className="text-lg font-semibold">Dharmiq</h1>
          <p className="text-muted-foreground text-xs">
            Legal information only — not legal advice. Consult a qualified lawyer for important decisions.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-muted-foreground hidden text-sm sm:inline">{user?.email}</span>
          <Button variant="outline" size="sm" onClick={logout}>
            Sign out
          </Button>
        </div>
      </header>

      <DebugPanel events={debugEvents} visible={Boolean(user?.is_superuser)} />

      <div className="flex min-h-0 flex-1">
        <aside className="border-border hidden w-72 shrink-0 flex-col gap-4 overflow-y-auto border-r p-3 md:flex">
          <div>
            <p className="text-muted-foreground mb-2 px-1 text-xs font-medium uppercase tracking-wide">
              Conversations
            </p>
            <ThreadList />
          </div>
          <UploadLibrary />
          <SessionAttachments sessionId={sessionId} />
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          {showProgress ? (
            <ProgressStepper
              steps={progressSteps}
              isActive={isRunning && streamStatus !== "done"}
              view={progressView}
              onViewChange={setProgressView}
            />
          ) : null}
          {slowNotice && isRunning ? (
            <div className="bg-muted/50 border-border border-b px-4 py-2 text-sm">
              This answer is taking longer than usual. Please wait; we&apos;re still working on it.
            </div>
          ) : null}
          {streamError ? (
            <div className="bg-destructive/10 text-destructive border-border border-b px-4 py-2 text-sm">
              {streamError}
            </div>
          ) : null}
          <div className="min-h-0 flex-1">
            <Thread />
          </div>
        </main>
      </div>
    </div>
  );
}

export function ChatPage() {
  return (
    <ChatRuntimeProvider>
      <ChatLayout />
    </ChatRuntimeProvider>
  );
}
