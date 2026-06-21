import {
  FileTextIcon,
  MessageSquareIcon,
  SettingsIcon,
  UserIcon,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import { chatSessionPath } from "@/lib/chatSession";
import { cn } from "@/lib/utils";

const tabs = [
  { id: "chat", label: "Chat", icon: MessageSquareIcon },
  {
    id: "documents",
    to: "/documents",
    label: "Docs",
    icon: FileTextIcon,
    end: false,
  },
  {
    id: "settings",
    to: "/settings",
    label: "Settings",
    icon: SettingsIcon,
    end: false,
  },
  {
    id: "account",
    to: "/settings",
    label: "Account",
    icon: UserIcon,
    end: false,
  },
] as const;

type MobileTabBarProps = {
  onNavigate?: () => void;
};

export function MobileTabBar({ onNavigate }: MobileTabBarProps) {
  const { pathname } = useLocation();
  const { sessionId } = useChatRuntimeState();
  const chatTo = sessionId ? chatSessionPath(sessionId) : "/";

  const isActive = (id: (typeof tabs)[number]["id"]) => {
    if (id === "chat") {
      return pathname === "/" || pathname.startsWith("/chat/");
    }
    if (id === "documents") {
      return pathname.startsWith("/documents");
    }
    return pathname.startsWith("/settings");
  };

  return (
    <nav className="border-border bg-card/92 flex border-t">
      {tabs.map((tab) => {
        const to = "to" in tab ? tab.to : chatTo;
        const end = "end" in tab ? tab.end : false;
        const { id, label, icon: Icon } = tab;
        return (
        <NavLink
          key={id}
          to={to}
          end={end}
          onClick={onNavigate}
          className={cn(
            "text-faint flex flex-1 flex-col items-center gap-0.5 py-2 text-[0.6em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            isActive(id) && "text-primary",
          )}
        >
          <Icon className="size-5" strokeWidth={1.7} />
          <span>{label}</span>
        </NavLink>
        );
      })}
    </nav>
  );
}
