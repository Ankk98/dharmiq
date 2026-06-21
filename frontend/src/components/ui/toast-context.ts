import { createContext } from "react";

export type ToastOptions = {
  title: string;
  detail?: string;
};

export type ToastContextValue = {
  toast: (options: ToastOptions) => void;
};

export const ToastContext = createContext<ToastContextValue | null>(null);
