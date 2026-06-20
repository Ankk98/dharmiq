import { useCallback, useEffect, useRef, useState } from "react";

import {
  chatRequestStreamUrl,
  getToken,
  parseSSEChunk,
  type ParsedSSEEvent,
  type StreamCitationPayload,
  type StreamProgressPayload,
} from "@/lib/api";
import { isDebugProgressPayload } from "@/lib/progress";

export type { ProgressStep, TurnProgress } from "@/lib/progress";

export type DebugEvent = StreamProgressPayload & {
  seq: number;
};

export type StreamStatus = "idle" | "connecting" | "streaming" | "done" | "error";

export type UseChatStreamCallbacks = {
  onProgress?: (payload: StreamProgressPayload) => void;
  onToken?: (token: string, accumulated: string) => void;
  onCitation?: (citation: StreamCitationPayload) => void;
  onDone?: (payload: ParsedSSEEvent & { type: "done" }) => void;
  onError?: (message: string, code?: string) => void;
};

export type StreamResult = {
  streamingText: string;
  streamCitations: StreamCitationPayload[];
  status: StreamStatus;
  errorMessage: string | null;
};

export function useChatStream(callbacks?: UseChatStreamCallbacks) {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [streamingText, setStreamingText] = useState("");
  const [streamCitations, setStreamCitations] = useState<StreamCitationPayload[]>([]);
  const [debugEvents, setDebugEvents] = useState<DebugEvent[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const callbacksRef = useRef(callbacks);

  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  const reset = useCallback(() => {
    setStatus("idle");
    setStreamingText("");
    setStreamCitations([]);
    setDebugEvents([]);
    setErrorMessage(null);
  }, []);

  const disconnect = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const handleEvent = useCallback((event: ParsedSSEEvent, accumulatedRef: { text: string }) => {
    switch (event.type) {
      case "progress": {
        const payload = event.data;
        if (isDebugProgressPayload(payload)) {
          setDebugEvents((prev) => [...prev, payload]);
        } else {
          callbacksRef.current?.onProgress?.(payload);
        }
        break;
      }
      case "answer_token": {
        accumulatedRef.text += event.data.token;
        setStreamingText(accumulatedRef.text);
        callbacksRef.current?.onToken?.(event.data.token, accumulatedRef.text);
        break;
      }
      case "citation": {
        setStreamCitations((prev) => [...prev, event.data]);
        callbacksRef.current?.onCitation?.(event.data);
        break;
      }
      case "error": {
        setErrorMessage(event.data.message);
        setStatus("error");
        callbacksRef.current?.onError?.(event.data.message, event.data.code);
        break;
      }
      case "done": {
        const doneStatus = String(event.data.status ?? "");
        if (doneStatus === "completed" || doneStatus === "COMPLETED") {
          setErrorMessage(null);
        }
        setStatus("done");
        callbacksRef.current?.onDone?.(event);
        break;
      }
    }
  }, []);

  const connect = useCallback(
    async (requestId: string, options?: { afterSeq?: number }): Promise<StreamResult> => {
      disconnect();
      reset();
      setStatus("connecting");

      const controller = new AbortController();
      abortRef.current = controller;
      const accumulatedRef = { text: "" };
      const citationsRef: { items: StreamCitationPayload[] } = { items: [] };
      let finalError: string | null = null;

      const token = getToken();
      const url = chatRequestStreamUrl(requestId, {
        afterSeq: options?.afterSeq,
        view: "detailed",
      });

      try {
        const response = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Stream failed (${response.status})`);
        }
        if (!response.body) {
          throw new Error("Stream body unavailable");
        }

        setStatus("streaming");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true });
          const parsed = parseSSEChunk(buffer);
          buffer = parsed.remainder;
          for (const event of parsed.events) {
            if (event.type === "citation") {
              citationsRef.items.push(event.data);
            }
            handleEvent(event, accumulatedRef);
            if (event.type === "error") {
              finalError = event.data.message;
            }
          }
        }

        if (buffer.trim()) {
          const parsed = parseSSEChunk(`${buffer}\n\n`);
          for (const event of parsed.events) {
            if (event.type === "citation") {
              citationsRef.items.push(event.data);
            }
            handleEvent(event, accumulatedRef);
          }
        }

        setStatus((current) => (current === "streaming" ? "done" : current));
      } catch (error) {
        if (controller.signal.aborted) {
          return {
            streamingText: accumulatedRef.text,
            streamCitations: citationsRef.items,
            status: "idle",
            errorMessage: null,
          };
        }
        const message = error instanceof Error ? error.message : "Stream connection failed";
        finalError = message;
        setErrorMessage(message);
        setStatus("error");
        callbacksRef.current?.onError?.(message);
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }

      return {
        streamingText: accumulatedRef.text,
        streamCitations: citationsRef.items,
        status: finalError ? "error" : "done",
        errorMessage: finalError,
      };
    },
    [disconnect, handleEvent, reset],
  );

  useEffect(() => () => disconnect(), [disconnect]);

  return {
    status,
    streamingText,
    streamCitations,
    debugEvents,
    errorMessage,
    connect,
    disconnect,
    reset,
  };
}
