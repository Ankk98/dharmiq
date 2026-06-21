import { useContext } from "react";

import {
  ChatRuntimeContext,
  type ChatRuntimeContextValue,
} from "@/providers/chat-runtime-context";

export function useChatRuntimeState(): ChatRuntimeContextValue {
  const context = useContext(ChatRuntimeContext);
  if (!context) {
    throw new Error("useChatRuntimeState must be used within ChatRuntimeProvider");
  }
  return context;
}
