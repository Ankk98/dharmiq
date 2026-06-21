import type { CSSProperties } from "react";
import {
  FileTextIcon,
  LogOutIcon,
  MessageSquareIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  SettingsIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { ThreadList } from "@/components/assistant-ui/thread-list";
import { Button } from "@/components/ui/button";
import { DefaultAvatar } from "@/components/ui/default-avatar";
import { useAuth } from "@/hooks/useAuth";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import { chatSessionPath } from "@/lib/chatSession";
import {
  SIDEBAR_COLLAPSED_WIDTH_PX,
  SIDEBAR_WIDTH_PX,
} from "@/lib/design/constants";
import { cn } from "@/lib/utils";

import { Wordmark } from "./Wordmark";

type AppSidebarProps = {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNavigate?: () => void;
  className?: string;
  style?: CSSProperties;
};

const navItems = [
  { id: "chat", label: "Chat", icon: MessageSquareIcon },
  { id: "documents", to: "/documents", label: "Documents", icon: FileTextIcon, end: false },
  { id: "settings", to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
] as const;

export function AppSidebar({
  collapsed,
  onToggleCollapse,
  onNavigate,
  className,
  style,
}: AppSidebarProps) {
  const { user, logout } = useAuth();
  const { sessionId } = useChatRuntimeState();
  const chatTo = sessionId ? chatSessionPath(sessionId) : "/";

  return (
    <aside
      className={cn(
        "border-sidebar-border bg-sidebar/92 flex shrink-0 flex-col gap-0.5 border-r p-3.5 transition-[width] duration-[var(--duration-slow)] ease-[var(--ease-default)]",
        className,
      )}
      style={{
        width: collapsed ? SIDEBAR_COLLAPSED_WIDTH_PX : SIDEBAR_WIDTH_PX,
        ...style,
      }}
    >
      <div className="mb-4 flex items-center justify-between">
        <Wordmark compact={collapsed} />
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          className="text-muted-foreground border-border bg-card shadow-[var(--card-highlight)] size-[26px] shrink-0 rounded-[7px]"
          onClick={onToggleCollapse}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpenIcon className="size-3.5" />
          ) : (
            <PanelLeftCloseIcon className="size-3.5" />
          )}
        </Button>
      </div>

      <nav className="flex flex-col gap-0.5">
        {navItems.map((item) => {
          const to = "to" in item ? item.to : chatTo;
          const end = "end" in item ? item.end : false;
          const { id, label, icon: Icon } = item;
          return (
          <NavLink
            key={id}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-2.5 rounded-[9px] px-2.5 py-2.5 text-[0.86em] transition-colors duration-[var(--duration-instant)] ease-[var(--ease-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                isActive
                  ? "bg-primary-muted text-primary font-medium"
                  : "text-muted-foreground hover:bg-border-subtle hover:text-foreground",
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive ? (
                  <span
                    aria-hidden
                    className="bg-primary shadow-[var(--glow)] absolute top-1/2 -left-3.5 h-[18px] w-[3px] -translate-y-1/2 rounded-r-[3px]"
                  />
                ) : null}
                <Icon className="size-[18px] shrink-0" strokeWidth={1.7} />
                {!collapsed ? <span>{label}</span> : null}
              </>
            )}
          </NavLink>
          );
        })}
      </nav>

      <div className="bg-border-subtle my-2.5 h-px" />

      {!collapsed ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <p className="text-faint mb-2 px-1 text-[0.72em] font-medium uppercase tracking-wide">
            Conversations
          </p>
          <ThreadList />
        </div>
      ) : (
        <div className="flex-1" />
      )}

      <div className="border-border-subtle mt-auto flex items-center gap-2 border-t pt-2">
        <DefaultAvatar />
        {!collapsed ? (
          <>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.78em] font-medium">{user?.email}</p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="icon-sm"
              className="text-muted-foreground size-7 shrink-0"
              onClick={logout}
              aria-label="Log out"
            >
              <LogOutIcon className="size-3.5" />
            </Button>
          </>
        ) : null}
      </div>
    </aside>
  );
}
