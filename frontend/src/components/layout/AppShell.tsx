import { useCallback, useState, type CSSProperties } from "react";
import { Outlet } from "react-router-dom";

import { DebugPanel } from "@/components/chat/DebugPanel";
import { useAuth } from "@/hooks/useAuth";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import {
  SIDEBAR_COLLAPSED_WIDTH_PX,
  SIDEBAR_WIDTH_PX,
} from "@/lib/design/constants";

import { AppSidebar } from "./AppSidebar";
import { AuroraBackground } from "./AuroraBackground";
import { MobileAppBar } from "./MobileAppBar";
import { MobileTabBar } from "./MobileTabBar";
import { TopNav } from "./TopNav";

export function AppShell() {
  const { user } = useAuth();
  const { debugEvents } = useChatRuntimeState();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((value) => !value);
  }, []);

  const closeMobileNav = useCallback(() => {
    setMobileNavOpen(false);
  }, []);

  const sidebarWidth = sidebarCollapsed
    ? SIDEBAR_COLLAPSED_WIDTH_PX
    : SIDEBAR_WIDTH_PX;

  const gridStyle = {
    gridTemplateColumns: `${sidebarWidth}px minmax(0, 1fr) 0px`,
  } satisfies CSSProperties;

  return (
    <div className="relative flex h-full overflow-hidden">
      <AuroraBackground />

      <div
        className="relative z-[1] hidden h-full min-h-0 w-full md:grid"
        style={gridStyle}
      >
        <AppSidebar collapsed={sidebarCollapsed} onToggleCollapse={toggleSidebar} />
        <MainColumn
          debugEvents={debugEvents}
          isSuperuser={Boolean(user?.is_superuser)}
        />
      </div>

      <div className="relative z-[1] flex h-full min-h-0 w-full flex-col md:hidden">
        {mobileNavOpen ? (
          <>
            <button
              type="button"
              aria-label="Close menu"
              className="fixed inset-0 z-40 bg-black/30"
              onClick={closeMobileNav}
            />
            <AppSidebar
              collapsed={false}
              onToggleCollapse={closeMobileNav}
              onNavigate={closeMobileNav}
              className="fixed inset-y-0 left-0 z-50"
              style={{ width: SIDEBAR_WIDTH_PX }}
            />
          </>
        ) : null}
        <MainColumn
          debugEvents={debugEvents}
          isSuperuser={Boolean(user?.is_superuser)}
          onMobileMenuOpen={() => setMobileNavOpen(true)}
          onNavigate={closeMobileNav}
        />
      </div>
    </div>
  );
}

type MainColumnProps = {
  debugEvents: ReturnType<typeof useChatRuntimeState>["debugEvents"];
  isSuperuser: boolean;
  onMobileMenuOpen?: () => void;
  onNavigate?: () => void;
};

function MainColumn({
  debugEvents,
  isSuperuser,
  onMobileMenuOpen,
  onNavigate,
}: MainColumnProps) {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {onMobileMenuOpen ? (
        <MobileAppBar onMenuClick={onMobileMenuOpen} />
      ) : null}

      <TopNav />

      <DebugPanel events={debugEvents} visible={isSuperuser} />

      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>

      {onNavigate ? <MobileTabBar onNavigate={onNavigate} /> : null}
    </div>
  );
}
