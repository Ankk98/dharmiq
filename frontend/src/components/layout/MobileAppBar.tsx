import { MenuIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DefaultAvatar } from "@/components/ui/default-avatar";

import { Wordmark } from "./Wordmark";

type MobileAppBarProps = {
  onMenuClick: () => void;
};

export function MobileAppBar({ onMenuClick }: MobileAppBarProps) {
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
      <DefaultAvatar className="size-7" />
    </header>
  );
}
