import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider, useAuth } from "@/lib/auth";
import { ChatPage } from "@/pages/ChatPage";
import { DocumentViewerPage } from "@/pages/DocumentViewerPage";
import { LoginPage } from "@/pages/LoginPage";
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

export default function App() {
  return (
    <AuthProvider>
      <TooltipProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <ChatPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/docs/:documentId"
            element={
              <ProtectedRoute>
                <DocumentViewerPage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </TooltipProvider>
    </AuthProvider>
  );
}
