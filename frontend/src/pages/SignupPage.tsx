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

export function SignupPage() {
  const { register, user, isLoading } = useAuth();
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
      await register(email, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <AuthForm
        onSubmit={onSubmit}
        submitLabel="Create account"
        submittingLabel="Creating account..."
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
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          minLength={8}
          placeholder="Create a password"
          required
        />
      </AuthForm>
      <AuthAltLink
        prompt="Already have an account?"
        linkText="Log in"
        to="/login"
      />
    </AuthLayout>
  );
}
