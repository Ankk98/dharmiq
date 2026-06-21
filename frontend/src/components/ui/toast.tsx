import { useCallback, useMemo, useState, type FC, type ReactNode } from "react";

import { ToastContext, type ToastOptions } from "@/components/ui/toast-context";
import { cn } from "@/lib/utils";

type ToastItem = ToastOptions & {
  id: string;
};

const TOAST_DURATION_MS = 3800;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const toast = useCallback((options: ToastOptions) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, ...options }]);

    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, TOAST_DURATION_MS);
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-relevant="additions"
        className="pointer-events-none fixed end-4 bottom-4 z-[100] flex w-[min(100%-2rem,22rem)] flex-col gap-2 md:end-6 md:bottom-6"
      >
        {toasts.map((item) => (
          <ToastView key={item.id} title={item.title} detail={item.detail} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const ToastView: FC<ToastOptions> = ({ title, detail }) => {
  return (
    <div
      role="status"
      className={cn(
        "toast-item border-border bg-raised flex items-center gap-[0.55rem] rounded-[10px] border px-3 py-2.5 text-[0.74rem] shadow-[var(--shadow-elevated)]",
      )}
    >
      <span
        className="bg-brand-accent grid size-[18px] shrink-0 place-items-center rounded-full text-[0.68rem] text-white"
        aria-hidden
      >
        ✓
      </span>
      <div className="min-w-0 leading-snug">
        <span className="font-semibold">{title}</span>
        {detail ? (
          <>
            {" "}
            <span className="text-muted-foreground">· {detail}</span>
          </>
        ) : null}
      </div>
    </div>
  );
};
