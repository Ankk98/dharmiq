import { UserMessageAttachments } from "@/components/assistant-ui/attachment";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { ClarifyCard } from "@/components/chat/ClarifyCard";
import { MessageProgress } from "@/components/chat/MessageProgress";
import { RefusalCard } from "@/components/chat/RefusalCard";
import { StreamingCaret } from "@/components/chat/StreamingCaret";
import {
  Reasoning,
  ReasoningContent,
  ReasoningRoot,
  ReasoningText,
  ReasoningTrigger,
} from "@/components/assistant-ui/reasoning";
import {
  ToolGroupContent,
  ToolGroupRoot,
  ToolGroupTrigger,
} from "@/components/assistant-ui/tool-group";
import { ToolFallback } from "@/components/assistant-ui/tool-fallback";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import type { ProgressView } from "@/lib/chatPreferences";
import { ComposerAttachmentChips } from "@/components/uploads/SessionAttachments";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import { READING_MEASURE } from "@/lib/design/constants";
import { messagePresentation } from "@/lib/messageMeta";
import { submitFeedback } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ActionBarMorePrimitive,
  ActionBarPrimitive,
  AuiIf,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  groupPartByType,
  MessagePrimitive,
  SuggestionPrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  MoreHorizontalIcon,
  PaperclipIcon,
  PencilIcon,
  RefreshCwIcon,
  SquareIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
} from "lucide-react";
import { type FC, useState } from "react";

export const Thread: FC = () => {
  return (
    <ThreadPrimitive.Root
      className="aui-root aui-thread-root bg-background @container flex h-full flex-col"
      style={{
        ["--thread-max-width" as string]: READING_MEASURE,
      }}
    >
      <ThreadPrimitive.Viewport
        turnAnchor="top"
        data-slot="aui_thread-viewport"
        className="relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll scroll-smooth"
      >
        <div className="mx-auto flex w-full max-w-(--thread-max-width) flex-1 flex-col px-4 pt-4">
          <AuiIf condition={(s) => s.thread.isEmpty}>
            <ThreadWelcome />
          </AuiIf>

          <div
            data-slot="aui_message-group"
            className="mb-10 flex flex-col gap-[1.1rem] empty:hidden"
          >
            <ThreadPrimitive.Messages>
              {() => <ThreadMessage />}
            </ThreadPrimitive.Messages>
          </div>

          <ThreadPrimitive.ViewportFooter className="aui-thread-viewport-footer border-border bg-card/70 sticky bottom-0 mt-auto flex flex-col gap-3 overflow-visible border-t px-0 pt-4 pb-4 md:pb-6">
            <ThreadScrollToBottom />
            <ProgressViewToggle />
            <Composer />
          </ThreadPrimitive.ViewportFooter>
        </div>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
};

const ThreadMessage: FC = () => {
  const role = useAuiState((s) => s.message.role);
  const isEditing = useAuiState((s) => s.message.composer.isEditing);

  if (isEditing) return <EditComposer />;
  if (role === "system") return <SystemEventMessage />;
  if (role === "user") return <UserMessage />;
  return <AssistantMessage />;
};

const SystemEventMessage: FC = () => {
  return (
    <MessagePrimitive.Root
      data-slot="aui_system-message-root"
      data-role="system"
      className="thread-msg-enter flex justify-center px-2"
    >
      <div className="text-muted-foreground bg-accent/70 inline-flex max-w-[90%] items-center gap-1.5 rounded-full border px-3 py-1.5 text-[0.74em] shadow-[var(--card-highlight)]">
        <PaperclipIcon className="size-3.5 shrink-0 stroke-[1.8]" />
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
};

const ThreadScrollToBottom: FC = () => {
  return (
    <ThreadPrimitive.ScrollToBottom
      render={
        <TooltipIconButton
          tooltip="Scroll to bottom"
          variant="outline"
          className="aui-thread-scroll-to-bottom border-border bg-background hover:bg-accent absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible"
        />
      }
    >
      <ArrowDownIcon />
    </ThreadPrimitive.ScrollToBottom>
  );
};

const ThreadWelcome: FC = () => {
  return (
    <div className="aui-thread-welcome-root my-auto flex grow flex-col">
      <div className="aui-thread-welcome-center flex w-full grow flex-col items-center justify-center">
        <div className="aui-thread-welcome-message flex size-full flex-col justify-center px-4 text-center @md:text-start">
          <h1 className="aui-thread-welcome-message-inner font-display text-2xl font-semibold tracking-tight">
            Know your rights
          </h1>
          <p className="aui-thread-welcome-message-inner text-muted-foreground mt-2 text-lg leading-relaxed">
            Ask about Indian law — grounded in statutory sources and your documents.
          </p>
        </div>
      </div>
      <ThreadSuggestions />
    </div>
  );
};

const ThreadSuggestions: FC = () => {
  return (
    <div className="aui-thread-welcome-suggestions grid w-full gap-2 pb-4 @md:grid-cols-2">
      <ThreadPrimitive.Suggestions>
        {() => <ThreadSuggestionItem />}
      </ThreadPrimitive.Suggestions>
    </div>
  );
};

const ThreadSuggestionItem: FC = () => {
  return (
    <div className="aui-thread-welcome-suggestion-display nth-[n+3]:hidden @md:nth-[n+3]:block">
      <SuggestionPrimitive.Trigger
        send
        render={
          <Button
            variant="ghost"
            className="aui-thread-welcome-suggestion bg-card hover:bg-accent h-auto w-full flex-wrap items-start justify-start gap-1 rounded-xl border px-4 py-3 text-start text-sm shadow-[var(--card-highlight)] transition-colors @md:flex-col"
          />
        }
      >
        <SuggestionPrimitive.Title className="aui-thread-welcome-suggestion-text-1 font-medium" />
        <SuggestionPrimitive.Description className="aui-thread-welcome-suggestion-text-2 text-muted-foreground empty:hidden" />
      </SuggestionPrimitive.Trigger>
    </div>
  );
};

const ProgressViewToggle: FC = () => {
  const { progressView, setProgressView, hasThreadProgress } = useChatRuntimeState();

  if (!hasThreadProgress) {
    return null;
  }

  const toggle = () => {
    const next: ProgressView =
      progressView === "detailed" ? "concise" : "detailed";
    setProgressView(next);
  };

  return (
    <div className="mx-auto flex w-full max-w-(--thread-max-width) justify-end">
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="text-muted-foreground border-border bg-card shadow-[var(--card-highlight)] h-auto px-2.5 py-1 text-[0.72em]"
        onClick={toggle}
      >
        {progressView === "detailed" ? "Concise view" : "Detailed view"}
      </Button>
    </div>
  );
};

const Composer: FC = () => {
  return (
    <ComposerPrimitive.Root className="aui-composer-root mx-auto flex w-full max-w-(--thread-max-width) flex-col gap-2.5">
      <ComposerAttachmentChips />
      <div className="flex items-end gap-2.5">
        <div
          data-slot="aui_composer-field"
          className="border-border bg-raised focus-within:border-primary focus-within:ring-primary/16 flex min-h-[50px] flex-1 items-center gap-1 rounded-[13px] border px-2 ps-3 shadow-[var(--card-highlight)] transition-[border-color,box-shadow] duration-150 focus-within:ring-[3px]"
        >
          <ComposerAttachButton />
          <ComposerPrimitive.Input
            placeholder="Ask about your rights…"
            className="aui-composer-input placeholder:text-faint max-h-32 min-h-[38px] flex-1 resize-none bg-transparent py-2.5 text-[0.86em] outline-none"
            rows={1}
            autoFocus
            aria-label="Message input"
          />
        </div>
        <ComposerSendButton />
      </div>
    </ComposerPrimitive.Root>
  );
};

const ComposerAttachButton: FC = () => {
  const { openAttachPicker, sessionId } = useChatRuntimeState();

  return (
    <button
      type="button"
      className="text-muted-foreground hover:text-primary hover:bg-accent composer-control grid size-9 shrink-0 place-items-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-40"
      aria-label="Attach documents"
      disabled={!sessionId}
      onClick={() => openAttachPicker()}
    >
      <PaperclipIcon className="size-[18px] stroke-[1.7]" />
    </button>
  );
};

const ComposerSendButton: FC = () => {
  return (
    <>
      <AuiIf condition={(s) => !s.thread.isRunning}>
        <ComposerPrimitive.Send
          render={
            <Button
              type="button"
              className="aui-composer-send h-[50px] min-w-[50px] shrink-0 rounded-[13px] px-4 text-[0.86em] font-medium shadow-[var(--glow)] active:scale-[0.96]"
              aria-label="Send message"
            >
              Send
            </Button>
          }
        />
      </AuiIf>
      <AuiIf condition={(s) => s.thread.isRunning}>
        <ComposerPrimitive.Cancel
          render={
            <Button
              type="button"
              size="icon"
              className="aui-composer-cancel size-[50px] shrink-0 rounded-[13px] shadow-[var(--glow)]"
              aria-label="Stop generating"
            />
          }
        >
          <SquareIcon className="size-3 fill-current" />
        </ComposerPrimitive.Cancel>
      </AuiIf>
    </>
  );
};

const MessageError: FC = () => {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root border-destructive bg-destructive/10 text-destructive mt-2 rounded-md border p-3 text-sm">
        <ErrorPrimitive.Message className="aui-message-error-message line-clamp-2" />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};

const AssistantMessage: FC = () => {
  const messageId = useAuiState((state) => state.message.id);
  const messageText = useAuiState((state) => {
    const part = state.message.content.find((item) => item.type === "text");
    return part?.type === "text" ? part.text : "";
  });
  const {
    getMessageProgress,
    getMessageMeta,
    progressView,
    streamingMessageId,
    streamStatus,
    activeClarifierMessageId,
  } = useChatRuntimeState();
  const progress = getMessageProgress(messageId);
  const presentation = messagePresentation(messageText, getMessageMeta(messageId));
  const isStreaming =
    messageId === streamingMessageId &&
    (streamStatus === "streaming" || streamStatus === "connecting");

  const ACTION_BAR_PT = "pt-1.5";
  const ACTION_BAR_HEIGHT = `-mb-7.5 min-h-7.5 ${ACTION_BAR_PT}`;

  if (presentation.kind === "progress") {
    if (!progress || progress.steps.length === 0) {
      return null;
    }

    return (
      <MessagePrimitive.Root
        data-slot="aui_assistant-message-root"
        data-role="assistant"
        className="thread-msg-enter relative flex justify-start px-2"
      >
        <MessageProgress progress={progress} view={progressView} />
      </MessagePrimitive.Root>
    );
  }

  if (presentation.kind === "clarifier") {
    const interactive =
      activeClarifierMessageId != null && messageId === activeClarifierMessageId;

    if (presentation.items.length === 0) {
      return (
        <MessagePrimitive.Root
          data-slot="aui_assistant-message-root"
          data-role="assistant"
          className="thread-msg-enter relative flex justify-start px-2"
        >
          <div className="border-border bg-raised text-muted-foreground w-full max-w-[min(72ch,100%)] rounded-[5px_14px_14px_14px] border p-4 text-[0.82em] shadow-[var(--card-highlight)]">
            Could not load follow-up questions
          </div>
        </MessagePrimitive.Root>
      );
    }

    return (
      <MessagePrimitive.Root
        data-slot="aui_assistant-message-root"
        data-role="assistant"
        className="thread-msg-enter relative flex justify-start px-2"
      >
        <ClarifyCard
          reason={presentation.reason}
          items={presentation.items}
          interactive={interactive}
        />
      </MessagePrimitive.Root>
    );
  }

  const showRefusal = presentation.kind === "refusal";

  return (
    <MessagePrimitive.Root
      data-slot="aui_assistant-message-root"
      data-role="assistant"
      className="thread-msg-enter relative"
      aria-busy={isStreaming}
    >
      {isStreaming ? (
        <span className="sr-only" aria-live="polite" aria-atomic="true">
          Answer is streaming
        </span>
      ) : null}
      <div
        data-slot="aui_assistant-message-content"
        className="text-foreground px-2 leading-relaxed wrap-break-word [contain-intrinsic-size:auto_24px] [content-visibility:auto] [lang=hi]:leading-[1.9]"
      >
        {showRefusal ? (
          <RefusalCard content={messageText} />
        ) : (
          <MessagePrimitive.GroupedParts
            groupBy={groupPartByType({
              reasoning: ["group-chainOfThought", "group-reasoning"],
              "tool-call": ["group-chainOfThought", "group-tool"],
              "standalone-tool-call": [],
            })}
          >
            {({ part, children }) => {
              switch (part.type) {
                case "group-chainOfThought":
                  return <div data-slot="aui_chain-of-thought">{children}</div>;
                case "group-reasoning": {
                  const running = part.status.type === "running";
                  return (
                    <ReasoningRoot defaultOpen={running}>
                      <ReasoningTrigger active={running} />
                      <ReasoningContent aria-busy={running}>
                        <ReasoningText>{children}</ReasoningText>
                      </ReasoningContent>
                    </ReasoningRoot>
                  );
                }
                case "group-tool":
                  return (
                    <ToolGroupRoot>
                      <ToolGroupTrigger
                        count={part.indices.length}
                        active={part.status.type === "running"}
                      />
                      <ToolGroupContent>{children}</ToolGroupContent>
                    </ToolGroupRoot>
                  );
                case "text":
                  return (
                    <>
                      <MarkdownText />
                      {isStreaming ? <StreamingCaret /> : null}
                    </>
                  );
                case "reasoning":
                  return <Reasoning {...part} />;
                case "tool-call":
                  return part.toolUI ?? <ToolFallback {...part} />;
                case "indicator":
                  return (
                    <span
                      data-slot="aui_assistant-message-indicator"
                      className="animate-pulse font-sans"
                      aria-label="Assistant is working"
                    >
                      {"●"}
                    </span>
                  );
                default:
                  return null;
              }
            }}
          </MessagePrimitive.GroupedParts>
        )}
        <MessageError />
      </div>

      {!showRefusal ? (
        <div
          data-slot="aui_assistant-message-footer"
          className={cn("ms-2 flex items-center", ACTION_BAR_HEIGHT)}
        >
          <BranchPicker hideWhenSingleBranch />
          <AssistantActionBar />
        </div>
      ) : null}
    </MessagePrimitive.Root>
  );
};

const AssistantActionBar: FC = () => {
  const messageId = useAuiState((s) => s.message.id);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleFeedback = async (rating: "up" | "down") => {
    if (submitting) {
      return;
    }
    const reason = window.prompt("Optional feedback reason (max 500 characters):") ?? undefined;
    setSubmitting(true);
    try {
      await submitFeedback(messageId, rating, reason);
      setFeedback(rating);
    } catch {
      // Keep the interaction lightweight: no global toast dependency here.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-assistant-action-bar-root text-faint col-start-3 row-start-2 -ms-1 flex gap-1.5"
    >
      <ActionBarPrimitive.Copy
        render={
          <TooltipIconButton
            tooltip="Copy"
            className="message-action-btn border-border-subtle text-faint hover:text-foreground hover:border-border hover:bg-accent size-[30px] rounded-lg border bg-transparent p-0"
          />
        }
      >
        <AuiIf condition={(s) => s.message.isCopied}>
          <CheckIcon className="size-[15px] stroke-[1.7]" />
        </AuiIf>
        <AuiIf condition={(s) => !s.message.isCopied}>
          <CopyIcon className="size-[15px] stroke-[1.7]" />
        </AuiIf>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.Reload
        render={
          <TooltipIconButton
            tooltip="Regenerate"
            className="message-action-btn border-border-subtle text-faint hover:text-foreground hover:border-border hover:bg-accent size-[30px] rounded-lg border bg-transparent p-0"
          />
        }
      >
        <RefreshCwIcon className="size-[15px] stroke-[1.7]" />
      </ActionBarPrimitive.Reload>
      <TooltipIconButton
        tooltip={feedback === "up" ? "Helpful (saved)" : "Helpful"}
        className={cn(
          "message-action-btn border-border-subtle text-faint hover:text-foreground hover:border-border hover:bg-accent size-[30px] rounded-lg border bg-transparent p-0",
          feedback === "up" && "text-foreground border-border bg-accent",
        )}
        onClick={() => void handleFeedback("up")}
        disabled={submitting}
      >
        <ThumbsUpIcon className="size-[15px] stroke-[1.7]" />
      </TooltipIconButton>
      <TooltipIconButton
        tooltip={feedback === "down" ? "Not helpful (saved)" : "Not helpful"}
        className={cn(
          "message-action-btn border-border-subtle text-faint hover:text-foreground hover:border-border hover:bg-accent size-[30px] rounded-lg border bg-transparent p-0",
          feedback === "down" && "text-foreground border-border bg-accent",
        )}
        onClick={() => void handleFeedback("down")}
        disabled={submitting}
      >
        <ThumbsDownIcon className="size-[15px] stroke-[1.7]" />
      </TooltipIconButton>
      <ActionBarMorePrimitive.Root>
        <ActionBarMorePrimitive.Trigger
          render={
            <TooltipIconButton
              tooltip="More"
              className="message-action-btn border-border-subtle text-faint hover:text-foreground hover:border-border hover:bg-accent data-[state=open]:bg-accent size-[30px] rounded-lg border bg-transparent p-0"
            />
          }
        >
          <MoreHorizontalIcon className="size-[15px] stroke-[1.7]" />
        </ActionBarMorePrimitive.Trigger>
        <ActionBarMorePrimitive.Content
          side="bottom"
          align="start"
          className="aui-action-bar-more-content bg-popover text-popover-foreground z-50 min-w-32 overflow-hidden rounded-md border p-1 shadow-md"
        >
          <ActionBarPrimitive.ExportMarkdown
            render={
              <ActionBarMorePrimitive.Item className="aui-action-bar-more-item hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none select-none" />
            }
          >
            <DownloadIcon className="size-4" />
            Export as Markdown
          </ActionBarPrimitive.ExportMarkdown>
        </ActionBarMorePrimitive.Content>
      </ActionBarMorePrimitive.Root>
    </ActionBarPrimitive.Root>
  );
};

const UserMessage: FC = () => {
  return (
    <MessagePrimitive.Root
      data-slot="aui_user-message-root"
      className="thread-msg-enter flex flex-col items-end gap-2 px-2 [contain-intrinsic-size:auto_60px] [content-visibility:auto]"
      data-role="user"
    >
      <UserMessageAttachments />

      <div className="aui-user-message-content-wrapper relative max-w-[82%] min-w-0">
        <div className="aui-user-message-content peer bg-primary text-primary-foreground empty:hidden rounded-[14px_14px_5px_14px] px-4 py-2.5 text-[0.92em] wrap-break-word shadow-[var(--glow)]">
          <MessagePrimitive.Parts />
        </div>
        <div className="aui-user-action-bar-wrapper absolute start-0 top-1/2 -translate-x-full -translate-y-1/2 pe-2 peer-empty:hidden rtl:translate-x-full">
          <UserActionBar />
        </div>
      </div>

      <BranchPicker
        hideWhenSingleBranch
        data-slot="aui_user-branch-picker"
        className="-me-1 justify-end"
      />
    </MessagePrimitive.Root>
  );
};

const UserActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-user-action-bar-root flex flex-col items-end"
    >
      <ActionBarPrimitive.Edit
        render={<TooltipIconButton tooltip="Edit" className="aui-user-action-edit p-4" />}
      >
        <PencilIcon />
      </ActionBarPrimitive.Edit>
    </ActionBarPrimitive.Root>
  );
};

const EditComposer: FC = () => {
  return (
    <MessagePrimitive.Root
      data-slot="aui_edit-composer-wrapper"
      className="thread-msg-enter flex flex-col px-2"
    >
      <ComposerPrimitive.Root className="aui-edit-composer-root bg-primary-muted ms-auto flex w-full max-w-[82%] flex-col rounded-[14px] border">
        <ComposerPrimitive.Input
          className="aui-edit-composer-input text-foreground min-h-14 w-full resize-none bg-transparent p-4 text-sm outline-none"
          autoFocus
        />
        <div className="aui-edit-composer-footer mx-3 mb-3 flex items-center gap-2 self-end">
          <ComposerPrimitive.Cancel render={<Button variant="ghost" size="sm" />}>
            Cancel
          </ComposerPrimitive.Cancel>
          <ComposerPrimitive.Send render={<Button size="sm" />}>Update</ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
    </MessagePrimitive.Root>
  );
};

const BranchPicker: FC<BranchPickerPrimitive.Root.Props> = ({
  className,
  hideWhenSingleBranch = true,
  ...rest
}) => {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch={hideWhenSingleBranch}
      className={cn(
        "aui-branch-picker-root text-muted-foreground -ms-2 me-2 inline-flex items-center text-xs",
        className,
      )}
      {...rest}
    >
      <BranchPickerPrimitive.Previous render={<TooltipIconButton tooltip="Previous" />}>
        <ChevronLeftIcon />
      </BranchPickerPrimitive.Previous>
      <span className="aui-branch-picker-state font-medium">
        <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
      </span>
      <BranchPickerPrimitive.Next render={<TooltipIconButton tooltip="Next" />}>
        <ChevronRightIcon />
      </BranchPickerPrimitive.Next>
    </BranchPickerPrimitive.Root>
  );
};
