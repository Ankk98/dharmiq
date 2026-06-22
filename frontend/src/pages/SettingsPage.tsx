import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { DefaultAvatar } from "@/components/ui/default-avatar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/hooks/useAuth";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import { useTheme, type Theme } from "@/hooks/useTheme";
import { useToast } from "@/hooks/useToast";
import { deleteAccount, exportAccount } from "@/lib/api";
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
            "border-border bg-card text-muted-foreground cursor-pointer rounded-lg border px-2.5 py-1.5 text-[0.74em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
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

function SettingsActionButton({
  children,
  danger = false,
  disabled = false,
  onClick,
}: {
  children: ReactNode;
  danger?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      className={cn(
        "border-border bg-card text-muted-foreground ml-auto shrink-0 cursor-pointer rounded-lg border px-2.5 py-1.5 text-[0.74em] transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        danger
          ? "text-destructive hover:bg-destructive hover:border-destructive hover:text-white"
          : "hover:text-foreground hover:border-ring",
      )}
      onClick={onClick}
    >
      {children}
    </button>
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
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const { progressView, setProgressView } = useChatRuntimeState();
  const [isExporting, setIsExporting] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteEmail, setDeleteEmail] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const { blob, filename } = await exportAccount();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
      toast({ title: "Export downloaded", detail: filename });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Export failed";
      toast({ title: "Export failed", detail: message });
    } finally {
      setIsExporting(false);
    }
  };

  const openDeleteModal = () => {
    setDeleteEmail(user?.email ?? "");
    setDeletePassword("");
    setDeleteError(null);
    setDeleteOpen(true);
  };

  const handleDelete = async () => {
    setDeleteError(null);
    setIsDeleting(true);
    try {
      await deleteAccount(deleteEmail, deletePassword);
      logout();
      navigate("/login", { replace: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Delete failed";
      setDeleteError(message);
    } finally {
      setIsDeleting(false);
    }
  };

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

        <SettingsCard title="Privacy & data">
          <SettingsRow
            title="Export my data"
            description="Full download (JSON)"
            control={
              <SettingsActionButton disabled={isExporting} onClick={handleExport}>
                {isExporting ? "Exporting…" : "Export"}
              </SettingsActionButton>
            }
          />
          <SettingsRow
            title="Delete account"
            description="Hard delete — irreversible"
            control={
              <SettingsActionButton danger onClick={openDeleteModal}>
                Delete
              </SettingsActionButton>
            }
          />
        </SettingsCard>

        <SettingsCard title="Account">
          <div className="border-border-subtle flex items-center gap-3 px-4 py-3">
            <DefaultAvatar className="size-[34px]" />
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

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete account</DialogTitle>
            <DialogDescription>
              This permanently deletes your account, chat history, uploads, and all associated
              data. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="delete-email">Email</Label>
              <Input
                id="delete-email"
                type="email"
                autoComplete="username"
                value={deleteEmail}
                onChange={(event) => setDeleteEmail(event.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="delete-password">Password</Label>
              <Input
                id="delete-password"
                type="password"
                autoComplete="current-password"
                value={deletePassword}
                onChange={(event) => setDeletePassword(event.target.value)}
              />
            </div>
            {deleteError ? (
              <p className="text-destructive text-[0.78em]" role="alert">
                {deleteError}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={isDeleting}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={isDeleting || !deleteEmail || !deletePassword}
              onClick={handleDelete}
            >
              {isDeleting ? "Deleting…" : "Delete account"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
