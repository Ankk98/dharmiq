import { MenuIcon } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

import { Wordmark } from "./Wordmark";

type MobileAppBarProps = {
  onMenuClick: () => void;
};

export function MobileAppBar({ onMenuClick }: MobileAppBarProps) {
  const { user } = useAuth();
  const emailInitial = user?.email?.charAt(0).toUpperCase() ?? "?";

  return (
    <header className="border-border bg-card/85 flex items-center gap-2.5 border-b px-4 py-2.5 md:hidden">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="text-muted-foreground"
        onClick={onMenuClick}
        aria-label="Open menu"
      >
        <MenuIcon className="size-5" strokeWidth={1.8} />
      </Button>
      <Wordmark className="flex-1" />
      <Avatar className="border-border-subtle bg-primary-muted text-primary size-7 border">
        <AvatarFallback className="bg-primary-muted text-primary text-[0.65em] font-medium">
          {emailInitial}
        </AvatarFallback>
      </Avatar>
    </header>
  );
}
