import type { FormEvent, ReactNode } from "react";
import { Link } from "react-router-dom";

import { AuroraBackground } from "@/components/layout/AuroraBackground";
import { Wordmark } from "@/components/layout/Wordmark";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type AuthLayoutProps = {
  children: ReactNode;
};

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="auth-layout relative grid min-h-full place-items-center bg-background p-6">
      <AuroraBackground />
      <div className="auth-card relative z-1 w-full max-w-[380px]">
        <Wordmark className="auth-wordmark mb-1.5 justify-center text-[1.3em]" />
        <p className="auth-tagline text-muted-foreground mb-5 text-center text-[0.78em]">
          Know your rights — grounded in the law.
        </p>
        {children}
        <p className="auth-foot text-faint mt-5 text-center text-[0.66em]">
          General legal information — not legal advice.
        </p>
      </div>
    </div>
  );
}

type AuthFieldProps = {
  id: string;
  label: string;
  type?: string;
  autoComplete?: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  minLength?: number;
  placeholder?: string;
};

export function AuthField({
  id,
  label,
  type = "text",
  autoComplete,
  value,
  onChange,
  required,
  minLength,
  placeholder,
}: AuthFieldProps) {
  return (
    <div className="auth-field mb-3">
      <Label htmlFor={id} className="auth-field-label text-muted-foreground mb-1 block text-[0.72em] font-normal">
        {label}
      </Label>
      <Input
        id={id}
        type={type}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        minLength={minLength}
        placeholder={placeholder}
        className="auth-field-input border-border bg-background h-11 rounded-[10px] px-3 text-[0.82em] hover:border-ring"
      />
    </div>
  );
}

type AuthFormProps = {
  onSubmit: (event: FormEvent) => void;
  children: ReactNode;
  submitLabel: string;
  submittingLabel: string;
  submitting: boolean;
  error?: string | null;
};

export function AuthForm({
  onSubmit,
  children,
  submitLabel,
  submittingLabel,
  submitting,
  error,
}: AuthFormProps) {
  return (
    <form onSubmit={onSubmit}>
      {children}
      {error ? (
        <p className="text-destructive auth-error mb-2 text-[0.76em]" role="alert">
          {error}
        </p>
      ) : null}
      <Button
        type="submit"
        disabled={submitting}
        className="auth-submit mt-1 h-[46px] w-full rounded-[11px] text-[0.85em] font-semibold shadow-[var(--glow)]"
      >
        {submitting ? submittingLabel : submitLabel}
      </Button>
    </form>
  );
}

type AuthAltLinkProps = {
  prompt: string;
  linkText: string;
  to: string;
};

export function AuthAltLink({ prompt, linkText, to }: AuthAltLinkProps) {
  return (
    <p className="text-muted-foreground mt-4 text-center text-[0.76em]">
      {prompt}{" "}
      <Link
        to={to}
        className={cn(
          "text-primary font-medium no-underline hover:underline",
        )}
      >
        {linkText}
      </Link>
    </p>
  );
}
