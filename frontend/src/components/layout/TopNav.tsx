import { useMemo } from "react";
import { useLocation } from "react-router-dom";

import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";

function routeLabel(pathname: string): string {
  if (pathname.startsWith("/documents")) {
    return "Documents";
  }
  if (pathname.startsWith("/settings")) {
    return "Settings";
  }
  if (pathname === "/" || pathname.startsWith("/chat/")) {
    return "Chat";
  }
  return "Chat";
}

export function TopNav() {
  const { pathname } = useLocation();
  const { sessions, sessionId } = useChatRuntimeState();

  const section = routeLabel(pathname);
  const sessionTitle = useMemo(() => {
    if (section !== "Chat" || !sessionId) {
      return null;
    }
    return sessions.find((session) => session.id === sessionId)?.title ?? "New chat";
  }, [section, sessionId, sessions]);

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
    </header>
  );
}
