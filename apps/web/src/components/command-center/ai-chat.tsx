"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  BoltIcon,
  BrainIcon,
  CheckCircleIcon,
  ConnectionIcon,
  LayersIcon,
  MicIcon,
  SendIcon,
  SparklesIcon,
  StopIcon,
} from "@/components/command-center/icons";
import { conversationApi, type StreamCompletedPayload } from "@/lib/api";
import { type ChatMessage, chatMessages, suggestedPrompts } from "@/lib/mock-data";

/** Build a display message from a completed backend conversation response. */
function toChatMessage(
  conversationId: string,
  response: string,
  metadata: StreamCompletedPayload,
  now: Date,
): ChatMessage {
  const time = now.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  return {
    id: `a-${conversationId}-${now.getTime()}`,
    role: "assistant",
    content: response,
    time,
    executionTime: metadata.execution_time_ms
      ? `${(metadata.execution_time_ms / 1000).toFixed(1)}s`
      : undefined,
  };
}

function ReasoningCard({ message }: { message: ChatMessage }) {
  return (
    <div className="mt-3 rounded-xl border border-indigo-400/10 bg-indigo-500/[0.06] p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-indigo-300">
        <BrainIcon className="h-3.5 w-3.5" />
        Reasoning Trace
      </div>
      <pre className="mt-2 scroll-thin whitespace-pre-wrap rounded-lg bg-black/20 p-2.5 font-mono text-[11px] leading-relaxed text-zinc-300">
        {message.reasoning}
      </pre>
    </div>
  );
}

function EvidenceSection({ message }: { message: ChatMessage }) {
  return (
    <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-zinc-300">
        <CheckCircleIcon className="h-3.5 w-3.5 text-emerald-400" />
        Evidence
      </div>
      <ul className="mt-2 flex flex-col gap-1.5">
        {message.evidence?.map((item) => (
          <li key={item} className="flex items-start gap-2 font-mono text-[11px] text-zinc-400">
            <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-emerald-400" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourcesSection({ message }: { message: ChatMessage }) {
  return (
    <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-zinc-300">
        <LayersIcon className="h-3.5 w-3.5 text-cyan-400" />
        Sources
      </div>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {message.sources?.map((source) => (
          <li
            key={source}
            className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-zinc-300 ring-1 ring-inset ring-white/10"
          >
            {source}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ToolsUsedChip({ message }: { message: ChatMessage }) {
  if (!message.toolsUsed?.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <ConnectionIcon className="h-3.5 w-3.5 text-zinc-500" />
      {message.toolsUsed.map((tool) => (
        <span
          key={tool}
          className="rounded-md bg-white/[0.06] px-2 py-0.5 font-mono text-[10px] text-zinc-300 ring-1 ring-inset ring-white/10"
        >
          {tool}
        </span>
      ))}
    </div>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const [_showTrace, _setShowTrace] = useState(false);
  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400/90 to-indigo-600 text-zinc-950 shadow-lg shadow-cyan-500/10">
        <SparklesIcon className="h-4.5 w-4.5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-zinc-100">Sentrix AI</span>
          <span className="rounded bg-emerald-400/10 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-emerald-300 ring-1 ring-inset ring-emerald-400/20">
            Verified
          </span>
          <span className="font-mono text-[10px] text-zinc-600">{message.executionTime}</span>
        </div>

        <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-200">
          {message.content}
        </p>

        <ReasoningCard message={message} />
        <EvidenceSection message={message} />
        <SourcesSection message={message} />
        <ToolsUsedChip message={message} />
      </div>
    </div>
  );
}

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%]">
        <p className="text-right text-[11px] text-zinc-500">{message.time}</p>
        <div className="mt-1 rounded-2xl rounded-tr-sm border border-cyan-400/10 bg-cyan-400/[0.12] px-4 py-2.5 text-[13px] leading-relaxed text-zinc-100">
          {message.content}
        </div>
      </div>
    </div>
  );
}

function TypingIndicator({ label = "Sentrix is reasoning…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-zinc-500">
      <span className="flex gap-1">
        <span className="typing-dot h-1.5 w-1.5 rounded-full bg-cyan-400" />
        <span className="typing-dot h-1.5 w-1.5 rounded-full bg-cyan-400 [animation-delay:120ms]" />
        <span className="typing-dot h-1.5 w-1.5 rounded-full bg-cyan-400 [animation-delay:240ms]" />
      </span>
      {label}
    </div>
  );
}

export function AiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(chatMessages);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamPhase, setStreamPhase] = useState<"thinking" | "generating" | "idle">("idle");
  const [selectedAgent, setSelectedAgent] = useState("SOC Agent");
  const [conversationId] = useState<string>(() =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `conv-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);

  const agents = [
    "SOC Agent",
    "Threat Hunt",
    "Malware Agent",
    "OSINT",
    "Compliance",
    "Report Agent",
  ];

  // Auto-scroll to the latest message whenever the thread changes. The effect
  // intentionally runs on messages/streaming/phase changes; scrollRef is stable.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see above.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, streaming, streamPhase]);

  const appendError = useCallback((message: string) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `err-${Date.now()}`,
        role: "assistant",
        content: `⚠ ${message}`,
        time: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      },
    ]);
  }, []);

  const stopStream = useCallback(() => {
    abortRef.current?.();
    abortRef.current = null;
    setStreaming(false);
    setStreamPhase("idle");
  }, []);

  async function submitPrompt(e: FormEvent) {
    e.preventDefault();
    const content = draft.trim();
    if (!content || streaming) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content,
      time: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };
    setMessages((prev) => [...prev, userMsg]);
    setDraft("");
    setStreaming(true);
    setStreamPhase("thinking");

    let acc = "";

    const handle = conversationApi.streamMessage(
      { conversation_id: conversationId, message: content },
      (event) => {
        switch (event.event) {
          case "status": {
            const payload = event.data as { status: string };
            setStreamPhase(payload.status === "generating" ? "generating" : "thinking");
            break;
          }
          case "token": {
            const payload = event.data as { token: string };
            acc += payload.token;
            setStreamPhase("generating");
            break;
          }
          case "completed": {
            const payload = event.data as StreamCompletedPayload;
            acc = payload.content;
            setMessages((prev) => [
              ...prev,
              toChatMessage(conversationId, payload.content, payload, new Date()),
            ]);
            break;
          }
          case "error": {
            const payload = event.data as { message: string };
            appendError(payload.message);
            break;
          }
          case "done": {
            // Terminal event — if a `completed` event was missed, commit the
            // accumulated tokens so the user never loses their reply.
            if (acc) {
              setMessages((prev) => {
                if (prev.some((m) => m.content === acc)) return prev;
                return [
                  ...prev,
                  {
                    id: `a-${conversationId}-${Date.now()}`,
                    role: "assistant",
                    content: acc,
                    time: new Date().toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    }),
                  },
                ];
              });
            }
            break;
          }
          default:
            break;
        }
      },
      (message) => {
        appendError(message);
      },
      () => {
        setStreaming(false);
        setStreamPhase("idle");
        abortRef.current = null;
      },
    );

    abortRef.current = handle.abort;
  }

  return (
    <section className="glass flex h-full min-h-0 flex-col overflow-hidden rounded-2xl">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-white/[0.06] px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400/90 to-indigo-600 text-zinc-950">
          <SparklesIcon className="h-4.5 w-4.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold text-zinc-100">AI Copilot</p>
          <p className="truncate text-[10px] text-zinc-500">
            Self-hosted · {selectedAgent}
            {streamPhase === "generating"
              ? " · streaming"
              : streamPhase === "thinking"
                ? " · thinking"
                : ""}
          </p>
        </div>
        <select
          value={selectedAgent}
          onChange={(e) => setSelectedAgent(e.target.value)}
          className="h-8 rounded-lg border border-white/[0.08] bg-white/[0.04] pl-2.5 pr-7 text-[11px] font-medium text-zinc-300 outline-none transition-colors focus:border-cyan-400/40"
          aria-label="Select agent"
        >
          {agents.map((agent) => (
            <option key={agent} value={agent} className="bg-zinc-900 text-zinc-200">
              {agent}
            </option>
          ))}
        </select>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] px-2.5 py-1 text-[10px] text-zinc-300 ring-1 ring-inset ring-white/10">
          <BoltIcon className="h-3 w-3 text-amber-300" />
          Real-time
        </span>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="scroll-thin min-h-0 flex-1 space-y-5 overflow-y-auto p-4 sm:p-5"
      >
        {messages.map((message) =>
          message.role === "user" ? (
            <UserMessage key={message.id} message={message} />
          ) : (
            <AssistantMessage key={message.id} message={message} />
          ),
        )}
        {streaming ? (
          <TypingIndicator
            label={
              streamPhase === "generating" ? "Sentrix is generating…" : "Sentrix is reasoning…"
            }
          />
        ) : null}
      </div>

      {/* Suggestions */}
      <div className="scroll-thin flex gap-2 overflow-x-auto border-t border-white/[0.04] px-4 py-2.5">
        {suggestedPrompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => setDraft(prompt)}
            className="shrink-0 rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-[11px] text-zinc-400 transition-colors hover:border-white/[0.16] hover:bg-white/[0.06] hover:text-zinc-200"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Composer */}
      <form
        onSubmit={submitPrompt}
        className="flex items-center gap-2 border-t border-white/[0.06] p-3"
      >
        <button
          type="button"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04] text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-zinc-200"
          aria-label="Voice input — coming soon"
          title="Voice input — coming soon"
        >
          <MicIcon className="h-4.5 w-4.5" />
        </button>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Ask ${selectedAgent}…`}
          disabled={streaming}
          className="h-9 min-w-0 flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 text-[13px] text-zinc-200 placeholder:text-zinc-600 outline-none transition-colors focus:border-cyan-400/40 focus:bg-white/[0.06] focus:ring-2 focus:ring-cyan-400/20 disabled:opacity-50"
        />
        {streaming ? (
          <button
            type="button"
            onClick={stopStream}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-red-500/90 text-white transition-all hover:bg-red-500"
            aria-label="Stop streaming"
            title="Stop streaming"
          >
            <StopIcon className="h-4 w-4" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!draft.trim() || streaming}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-600 text-zinc-950 transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Send message"
          >
            <SendIcon className="h-4.5 w-4.5" />
          </button>
        )}
      </form>
    </section>
  );
}
