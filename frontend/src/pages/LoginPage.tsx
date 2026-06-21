import type { FormEvent } from "react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import {
  AuthAltLink,
  AuthField,
  AuthForm,
  AuthLayout,
} from "@/components/auth/AuthLayout";
import { useAuth } from "@/hooks/useAuth";

export function LoginPage() {
  const { login, user, isLoading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (!isLoading && user) {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <AuthForm
        onSubmit={onSubmit}
        submitLabel="Log in"
        submittingLabel="Logging in..."
        submitting={submitting}
        error={error}
      >
        <AuthField
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={setEmail}
          required
        />
        <AuthField
          id="password"
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
          required
        />
      </AuthForm>
      <AuthAltLink
        prompt="New here?"
        linkText="Create an account"
        to="/signup"
      />
    </AuthLayout>
  );
}
