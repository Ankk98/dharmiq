import { useMemo } from "react";
import { useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import type { ProgressView } from "@/lib/chatPreferences";
import { cn } from "@/lib/utils";

function routeLabel(pathname: string): string {
  if (pathname.startsWith("/documents")) {
    return "Documents";
  }
  if (pathname.startsWith("/settings")) {
    return "Settings";
  }
  return "Chat";
}

export function TopNav() {
  const { pathname } = useLocation();
  const { progressView, setProgressView, sessions, sessionId } =
    useChatRuntimeState();

  const section = routeLabel(pathname);
  const sessionTitle = useMemo(() => {
    if (section !== "Chat" || !sessionId) {
      return null;
    }
    return sessions.find((session) => session.id === sessionId)?.title ?? "New chat";
  }, [section, sessionId, sessions]);

  const toggleProgressView = () => {
    const next: ProgressView =
      progressView === "detailed" ? "concise" : "detailed";
    setProgressView(next);
  };

  return (
    <header className="border-border bg-card/80 sticky top-0 z-10 flex items-center gap-3 border-b px-5 py-2.5 backdrop-blur-sm">
      <div className="text-muted-foreground min-w-0 text-[0.84em]">
        <span>{section}</span>
        {sessionTitle ? (
          <>
            {" "}
            · <span className="text-foreground font-medium">{sessionTitle}</span>
          </>
        ) : null}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <span
          className={cn(
            "border-border text-muted-foreground inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.72em] shadow-[var(--card-highlight)]",
          )}
        >
          <span className="bg-brand-accent relative size-1.5 rounded-full">
            <span className="bg-brand-accent/50 absolute inset-0 animate-ping rounded-full" />
          </span>
          grounded
        </span>

        <Button
          type="button"
          variant="outline"
          size="sm"
          className="text-muted-foreground border-border bg-card shadow-[var(--card-highlight)] h-auto px-2.5 py-1.5 text-[0.78em]"
          onClick={toggleProgressView}
        >
          {progressView === "detailed" ? "Concise view" : "Detailed view"}
        </Button>
      </div>
    </header>
  );
}
