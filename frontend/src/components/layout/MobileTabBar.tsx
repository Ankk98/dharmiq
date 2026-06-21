import {
  FileTextIcon,
  MessageSquareIcon,
  SettingsIcon,
  UserIcon,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

const tabs = [
  { to: "/", label: "Chat", icon: MessageSquareIcon, end: true, id: "chat" },
  {
    to: "/documents",
    label: "Docs",
    icon: FileTextIcon,
    end: false,
    id: "documents",
  },
  {
    to: "/settings",
    label: "Settings",
    icon: SettingsIcon,
    end: false,
    id: "settings",
  },
  {
    to: "/settings",
    label: "Account",
    icon: UserIcon,
    end: false,
    id: "account",
  },
] as const;

type MobileTabBarProps = {
  onNavigate?: () => void;
};

export function MobileTabBar({ onNavigate }: MobileTabBarProps) {
  const { pathname } = useLocation();

  const isActive = (id: (typeof tabs)[number]["id"]) => {
    if (id === "chat") {
      return pathname === "/";
    }
    if (id === "documents") {
      return pathname.startsWith("/documents");
    }
    return pathname.startsWith("/settings");
  };

  return (
    <nav className="border-border bg-card/92 flex border-t">
      {tabs.map(({ to, label, icon: Icon, end, id }) => (
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
      ))}
    </nav>
  );
}
