import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";
import { useAuth } from "@/hooks/useAuth";
import { ChatRuntimeProvider } from "@/providers/ChatRuntimeProvider";
import { DocumentPanelProvider } from "@/providers/DocumentPanelProvider";
import { ChatPage } from "@/pages/ChatPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { LoginPage } from "@/pages/LoginPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SignupPage } from "@/pages/SignupPage";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground text-sm">Loading...</p>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function AuthenticatedShell() {
  return (
    <ProtectedRoute>
      <ChatRuntimeProvider>
        <DocumentPanelProvider>
          <AppShell />
        </DocumentPanelProvider>
      </ChatRuntimeProvider>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <TooltipProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route element={<AuthenticatedShell />}>
              <Route index element={<ChatPage />} />
              <Route path="documents" element={<DocumentsPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="docs/:documentId" element={<ChatPage />} />
            </Route>
          </Routes>
        </TooltipProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
