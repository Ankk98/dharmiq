import type { ReactNode } from "react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useAuth } from "@/hooks/useAuth";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import { useTheme, type Theme } from "@/hooks/useTheme";
import type { ProgressView } from "@/lib/chatPreferences";
import { cn } from "@/lib/utils";

type OptionToggleProps<T extends string> = {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
};

function OptionToggle<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: OptionToggleProps<T>) {
  return (
    <div
      className="ml-auto flex gap-1.5"
      role="group"
      aria-label={ariaLabel}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          className={cn(
            "border-border bg-card text-muted-foreground cursor-pointer rounded-lg border px-2.5 py-1.5 text-[0.74em] transition-colors",
            value === option.value &&
              "bg-primary-muted text-primary border-primary font-medium",
          )}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function SettingsCard({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="border-border bg-card overflow-hidden rounded-xl border shadow-[var(--card-highlight)]">
      <h2 className="border-border-subtle border-b px-4 py-3.5 text-[0.82em] font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function SettingsRow({
  title,
  description,
  control,
}: {
  title: string;
  description?: string;
  control: ReactNode;
}) {
  return (
    <div className="border-border-subtle flex items-center gap-3 border-b px-4 py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-[0.82em]">{title}</p>
        {description ? (
          <p className="text-muted-foreground mt-0.5 text-[0.72em]">{description}</p>
        ) : null}
      </div>
      {control}
    </div>
  );
}

const PROGRESS_OPTIONS = [
  { value: "concise" as const, label: "Concise" },
  { value: "detailed" as const, label: "Detailed" },
] satisfies readonly { value: ProgressView; label: string }[];

const THEME_OPTIONS = [
  { value: "light" as const, label: "Light" },
  { value: "dark" as const, label: "Dark" },
] satisfies readonly { value: Theme; label: string }[];

export function SettingsPage() {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const { progressView, setProgressView } = useChatRuntimeState();

  const emailInitial = user?.email?.charAt(0).toUpperCase() ?? "?";

  return (
    <div className="flex-1 overflow-y-auto p-6 max-md:p-4">
      <h1 className="font-display mb-1 text-[1.25em] font-semibold">Settings</h1>
      <p className="text-muted-foreground mb-[1.1rem] text-[0.8em]">
        You own your data. Configure how Dharmiq works for you.
      </p>

      <div className="flex max-w-[680px] flex-col gap-4">
        <SettingsCard title="Answer progress">
          <SettingsRow
            title="Progress detail"
            description="How much of the agent pipeline you see"
            control={
              <OptionToggle
                ariaLabel="Answer progress detail"
                options={PROGRESS_OPTIONS}
                value={progressView}
                onChange={setProgressView}
              />
            }
          />
        </SettingsCard>

        <SettingsCard title="Appearance">
          <SettingsRow
            title="Theme"
            description="Ashoka"
            control={
              <OptionToggle
                ariaLabel="Color theme"
                options={THEME_OPTIONS}
                value={theme}
                onChange={setTheme}
              />
            }
          />
        </SettingsCard>

        <SettingsCard title="Account">
          <div className="border-border-subtle flex items-center gap-3 px-4 py-3">
            <Avatar className="border-border-subtle bg-primary-muted text-primary size-[34px] border shadow-[var(--card-highlight)]">
              <AvatarFallback className="bg-primary-muted text-primary text-xs font-medium">
                {emailInitial}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.82em] font-medium">{user?.email}</p>
            </div>
            <button
              type="button"
              className="border-border bg-card text-muted-foreground hover:text-foreground hover:border-ring ml-auto shrink-0 cursor-pointer rounded-lg border px-2.5 py-1.5 text-[0.74em] transition-colors"
              onClick={logout}
            >
              Log out
            </button>
          </div>
        </SettingsCard>
      </div>
    </div>
  );
}
