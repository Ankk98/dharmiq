import { UserMessageAttachments } from "@/components/assistant-ui/attachment";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { MessageProgress } from "@/components/chat/MessageProgress";
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
import { ComposerAttachmentChips } from "@/components/uploads/SessionAttachments";
import { useChatRuntimeState } from "@/hooks/useChatRuntimeState";
import { READING_MEASURE } from "@/lib/design/constants";
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
  MicIcon,
  MoreHorizontalIcon,
  PaperclipIcon,
  PencilIcon,
  RefreshCwIcon,
  SquareIcon,
} from "lucide-react";
import type { FC } from "react";

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

const Composer: FC = () => {
  const { awaitingClarification, forceAnswer, isRunning } = useChatRuntimeState();

  return (
    <ComposerPrimitive.Root className="aui-composer-root mx-auto flex w-full max-w-(--thread-max-width) flex-col gap-2.5">
      <ComposerAttachmentChips />
      {awaitingClarification && !isRunning ? (
        <div className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="border-dashed text-xs"
            onClick={() => void forceAnswer()}
          >
            Answer with what you have
          </Button>
        </div>
      ) : null}
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
          <span
            className="text-muted-foreground grid size-9 shrink-0 place-items-center rounded-lg opacity-40"
            title="Voice (coming soon)"
            aria-hidden
          >
            <MicIcon className="size-[18px] stroke-[1.7]" />
          </span>
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
      className="text-muted-foreground hover:text-primary hover:bg-accent grid size-9 shrink-0 place-items-center rounded-lg transition-colors disabled:opacity-40"
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
  const { getMessageProgress, progressView, setProgressView } = useChatRuntimeState();
  const progress = getMessageProgress(messageId);

  const ACTION_BAR_PT = "pt-1.5";
  const ACTION_BAR_HEIGHT = `-mb-7.5 min-h-7.5 ${ACTION_BAR_PT}`;

  return (
    <MessagePrimitive.Root
      data-slot="aui_assistant-message-root"
      data-role="assistant"
      className="thread-msg-enter relative"
    >
      <div
        data-slot="aui_assistant-message-content"
        className="text-foreground px-2 leading-relaxed wrap-break-word [contain-intrinsic-size:auto_24px] [content-visibility:auto]"
      >
        {progress && progress.steps.length > 0 ? (
          <MessageProgress
            progress={progress}
            view={progressView}
            onViewChange={setProgressView}
            defaultOpen={progress.status === "running"}
          />
        ) : null}
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
                return <MarkdownText />;
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
        <MessageError />
      </div>

      <div
        data-slot="aui_assistant-message-footer"
        className={cn("ms-2 flex items-center", ACTION_BAR_HEIGHT)}
      >
        <BranchPicker />
        <AssistantActionBar />
      </div>
    </MessagePrimitive.Root>
  );
};

const AssistantActionBar: FC = () => {
  return (
    <ActionBarPrimitive.Root
      hideWhenRunning
      autohide="not-last"
      className="aui-assistant-action-bar-root text-muted-foreground col-start-3 row-start-2 -ms-1 flex gap-1"
    >
      <ActionBarPrimitive.Copy render={<TooltipIconButton tooltip="Copy" />}>
        <AuiIf condition={(s) => s.message.isCopied}>
          <CheckIcon />
        </AuiIf>
        <AuiIf condition={(s) => !s.message.isCopied}>
          <CopyIcon />
        </AuiIf>
      </ActionBarPrimitive.Copy>
      <ActionBarPrimitive.Reload render={<TooltipIconButton tooltip="Refresh" />}>
        <RefreshCwIcon />
      </ActionBarPrimitive.Reload>
      <ActionBarMorePrimitive.Root>
        <ActionBarMorePrimitive.Trigger
          render={
            <TooltipIconButton tooltip="More" className="data-[state=open]:bg-accent" />
          }
        >
          <MoreHorizontalIcon />
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
  ...rest
}) => {
  return (
    <BranchPickerPrimitive.Root
      hideWhenSingleBranch
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
