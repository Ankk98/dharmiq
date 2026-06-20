import { useCallback, useEffect, useRef, useState } from "react";

import {
  chatRequestStreamUrl,
  getToken,
  parseSSEChunk,
  type ParsedSSEEvent,
  type StreamCitationPayload,
  type StreamProgressPayload,
} from "@/lib/api";
import type { ProgressView } from "@/lib/chatPreferences";

export type ProgressStep = {
  stepId: string;
  label: string;
  status: "running" | "completed" | "failed";
  agent?: string;
  chunkCount?: number;
  preview?: string[];
};

export type DebugEvent = StreamProgressPayload & {
  seq: number;
};

export type StreamStatus = "idle" | "connecting" | "streaming" | "done" | "error";

export type UseChatStreamCallbacks = {
  onProgress?: (step: ProgressStep) => void;
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

function upsertStep(
  steps: Map<string, ProgressStep>,
  payload: StreamProgressPayload,
): Map<string, ProgressStep> {
  const stepId = payload.step_id ?? payload.label;
  const next = new Map(steps);
  next.set(stepId, {
    stepId,
    label: payload.label,
    status: payload.status,
    agent: payload.agent,
    chunkCount: payload.chunk_count,
    preview: payload.preview,
  });
  return next;
}

function isDebugPayload(payload: StreamProgressPayload): boolean {
  return (
    payload.rerank_scores != null ||
    payload.queries != null ||
    payload.validator_issues != null ||
    payload.chunk_snippets != null ||
    payload.token_breakdown != null
  );
}

export function useChatStream(view: ProgressView, callbacks?: UseChatStreamCallbacks) {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [steps, setSteps] = useState<Map<string, ProgressStep>>(new Map());
  const [streamingText, setStreamingText] = useState("");
  const [streamCitations, setStreamCitations] = useState<StreamCitationPayload[]>([]);
  const [debugEvents, setDebugEvents] = useState<DebugEvent[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastSeq, setLastSeq] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  const callbacksRef = useRef(callbacks);

  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  const reset = useCallback(() => {
    setStatus("idle");
    setSteps(new Map());
    setStreamingText("");
    setStreamCitations([]);
    setDebugEvents([]);
    setErrorMessage(null);
    setLastSeq(0);
  }, []);

  const disconnect = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const handleEvent = useCallback((event: ParsedSSEEvent, accumulatedRef: { text: string }) => {
    const seq = "seq" in event.data ? (event.data.seq as number) : 0;
    if (seq > 0) {
      setLastSeq((prev) => Math.max(prev, seq));
    }

    switch (event.type) {
      case "progress": {
        const payload = event.data;
        if (isDebugPayload(payload)) {
          setDebugEvents((prev) => [...prev, payload]);
        } else {
          setSteps((prev) => {
            const updated = upsertStep(prev, payload);
            const stepId = payload.step_id ?? payload.label;
            const step = updated.get(stepId);
            if (step) {
              callbacksRef.current?.onProgress?.(step);
            }
            return updated;
          });
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
        view,
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
    [disconnect, handleEvent, reset, view],
  );

  useEffect(() => () => disconnect(), [disconnect]);

  const progressSteps = Array.from(steps.values());

  return {
    status,
    progressSteps,
    streamingText,
    streamCitations,
    debugEvents,
    errorMessage,
    lastSeq,
    connect,
    disconnect,
    reset,
  };
}
