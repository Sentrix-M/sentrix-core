"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  BoltIcon,
  BrainIcon,
  CheckCircleIcon,
  ConnectionIcon,
  LayersIcon,
  MicIcon,
  PlayIcon,
  SendIcon,
  SparklesIcon,
  StopIcon,
} from "@/components/command-center/icons";
import { conversationApi, getAccessToken, ttsApi, type StreamCompletedPayload } from "@/lib/api";
import { type ChatMessage, chatMessages, suggestedPrompts } from "@/lib/mock-data";

/** Voice input UI states (Phase 16B). */
type VoiceState = "idle" | "listening" | "transcribing" | "thinking" | "speaking";

const VOICE_LABELS: Record<VoiceState, string> = {
  idle: "🎤 Idle",
  listening: "🎙 Listening…",
  transcribing: "📝 Transcribing…",
  thinking: "🤖 Thinking…",
  speaking: "🗣 Speaking…",
};

/** WebSocket base URL derived from the REST API URL (http→ws, https→wss). */
const API_WS_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
  .replace(/^https/, "wss")
  .replace(/^http/, "ws");

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

export function AiChat({ autoStartVoice = false }: { autoStartVoice?: boolean }) {
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

  // Voice input (Phase 16B) — mic permission, MediaRecorder, WS→STT.
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [partialTranscript, setPartialTranscript] = useState("");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const finalTranscriptRef = useRef<string | null>(null);

  // Voice output (Phase 16C) — TTS playback state/refs.
  const [speaking, setSpeaking] = useState(false);
  const [lastSpoken, setLastSpoken] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

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

  // ------------------------------------------------------------------
  // Voice output (Phase 16C) — TTS playback
  // ------------------------------------------------------------------

  /** Stop any currently playing utterance and release the audio object URL. */
  const stopSpeaking = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setSpeaking(false);
  }, []);

  /** Synthesize ``text`` via the backend TTS endpoint and play it. */
  const speakText = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content) return;

      // Stop any current playback before starting a new utterance (cancellable).
      stopSpeaking();

      try {
        const blob = await ttsApi.synthesize(content);
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;

        const audio = new Audio(url);
        audioRef.current = audio;
        setLastSpoken(content);
        setSpeaking(true);

        audio.onended = () => {
          stopSpeaking();
        };
        audio.onerror = () => {
          stopSpeaking();
        };

        await audio.play();
      } catch (err) {
        stopSpeaking();
        const message = err instanceof Error ? err.message : "Speech synthesis failed.";
        appendError(message);
      }
    },
    [stopSpeaking, appendError],
  );

  // On unmount, clean up any in-flight audio.
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, []);

  // ------------------------------------------------------------------
  // Voice input (Phase 16B)
  // ------------------------------------------------------------------

  /** Send the final transcript through the existing chat submit flow. */
  const submitVoiceTranscript = useCallback(
    (transcript: string) => {
      const content = transcript.trim();
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
              void speakText(payload.content);
              break;
            }
            case "error": {
              const payload = event.data as { message: string };
              appendError(payload.message);
              break;
            }
            case "done": {
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
    },
    [conversationId, streaming, appendError, speakText],
  );

  /** Tear down the active WS + media tracks + recorder. */
  const teardownVoice = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // Ignore — recorder may already be inactive.
      }
    }
    mediaRecorderRef.current = null;
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        // Ignore
      }
    }
    wsRef.current = null;
    if (streamRef.current) {
      for (const track of streamRef.current.getTracks()) track.stop();
    }
    streamRef.current = null;
  }, []);

  /** Start microphone capture + the voice WS→STT session. */
  const startVoice = useCallback(async () => {
    if (streaming) {
      appendError("Please wait for the current response to finish before using voice.");
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      appendError("Voice input is not supported in this browser.");
      return;
    }
    const token = getAccessToken();
    if (!token) {
      appendError("You must be signed in to use voice input.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: false,
      });
      streamRef.current = stream;

      // Open the voice WebSocket (auth via ?token= for browser compatibility).
      const ws = new WebSocket(
        `${API_WS_BASE}/api/v1/voice/transcribe?token=${encodeURIComponent(token)}`,
      );
      wsRef.current = ws;

      ws.onmessage = (event) => {
        let payload: {
          type?: string;
          text?: string;
          detail?: string;
          final?: boolean;
        };
        try {
          payload = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (payload.type === "transcript" && payload.text) {
          setPartialTranscript(payload.text);
          if (payload.final) {
            finalTranscriptRef.current = payload.text;
          }
        } else if (payload.type === "error") {
          // Surface voice failures instead of leaving the UI in "Listening…".
          const detail = payload.detail || payload.text || "Voice transcription failed.";
          teardownVoice();
          setPartialTranscript("");
          setVoiceState("idle");
          appendError(detail);
        }
      };

      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () => reject(new Error("Could not connect to the voice service."));
      });

      // Send the config event so the utterance routes to the same conversation.
      ws.send(JSON.stringify({ type: "config", conversation_id: conversationId }));

      // Start recording PCM-ish audio chunks and stream them to the server.
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(e.data);
        }
      };
      recorder.start(250);

      setVoiceState("listening");
      setPartialTranscript("");
      finalTranscriptRef.current = null;
    } catch (err) {
      teardownVoice();
      setVoiceState("idle");
      const message = err instanceof Error ? err.message : "Could not access the microphone.";
      appendError(message);
    }
  }, [conversationId, streaming, appendError, teardownVoice]);

  /** Stop recording, signal end-of-speech, and route the transcript to chat. */
  const stopVoice = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(e.data);
        }
      };
      recorder.stop();
    }

    setVoiceState("transcribing");

    // Signal end-of-speech so the server transcribes once.
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "end" }));
    }

    // Wait for the final transcript, then submit via the existing chat flow.
    const poll = setInterval(() => {
      const transcript = finalTranscriptRef.current;
      if (transcript) {
        clearInterval(poll);
        setPartialTranscript("");
        setVoiceState("thinking");
        teardownVoice();
        submitVoiceTranscript(transcript);
        return;
      }
      if (!wsRef.current) {
        // Socket closed without a final transcript — reset.
        clearInterval(poll);
        setPartialTranscript("");
        setVoiceState("idle");
      }
    }, 150);

    // Safety timeout — never leave the UI stuck transcribing.
    setTimeout(() => {
      clearInterval(poll);
      const transcript = finalTranscriptRef.current;
      if (transcript) {
        setPartialTranscript("");
        setVoiceState("thinking");
        teardownVoice();
        submitVoiceTranscript(transcript);
      } else {
        setPartialTranscript("");
        setVoiceState("idle");
        teardownVoice();
      }
    }, 15000);
  }, [submitVoiceTranscript, teardownVoice]);

  /** Toggle voice input on the mic button. */
  const toggleVoice = useCallback(() => {
    if (voiceState === "listening") {
      void stopVoice();
    } else {
      void startVoice();
    }
  }, [voiceState, startVoice, stopVoice]);

  // Auto-start the Phase 16B voice flow when the Voice Orb navigates here
  // with `?voice=1`. Reuses the existing startVoice() — no new voice state.
  useEffect(() => {
    if (autoStartVoice) {
      void startVoice();
    }
    // Only fire once on mount with the initial intent.
    // biome-ignore lint/correctness/useExhaustiveDependencies: one-shot intent.
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => teardownVoice();
  }, [teardownVoice]);

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
            void speakText(payload.content);
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
        {speaking || lastSpoken ? (
          <button
            type="button"
            onClick={() => {
              if (speaking) {
                stopSpeaking();
              } else if (lastSpoken) {
                void speakText(lastSpoken);
              }
            }}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-colors ${
              speaking
                ? "border-indigo-400/40 bg-indigo-500/20 text-indigo-300"
                : "border-white/[0.08] bg-white/[0.04] text-zinc-400 hover:bg-white/[0.08] hover:text-zinc-200"
            }`}
            aria-label={speaking ? "Stop speaking" : "Replay last response"}
            title={speaking ? "Stop speaking" : "Replay last response"}
          >
            {speaking ? (
              <StopIcon className="h-4 w-4" />
            ) : (
              <PlayIcon className="h-4.5 w-4.5" />
            )}
          </button>
        ) : null}
        <button
          type="button"
          onClick={toggleVoice}
          disabled={streaming}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-colors ${
            voiceState === "listening"
              ? "border-red-400/40 bg-red-500/20 text-red-300"
              : "border-white/[0.08] bg-white/[0.04] text-zinc-400 hover:bg-white/[0.08] hover:text-zinc-200"
          } disabled:cursor-not-allowed disabled:opacity-40`}
          aria-label={voiceState === "listening" ? "Stop voice input" : "Speak to the AI"}
          title={voiceState === "listening" ? "Stop recording" : "Speak to the AI"}
        >
          <MicIcon className="h-4.5 w-4.5" />
        </button>
        {voiceState !== "idle" ? (
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-cyan-400/20 bg-cyan-400/[0.06] px-3 py-2">
            <span className="truncate text-[12px] text-zinc-300">
              {VOICE_LABELS[voiceState] || "Voice"}
            </span>
            {partialTranscript ? (
              <span className="truncate font-mono text-[11px] text-cyan-300">
                “{partialTranscript}”
              </span>
            ) : null}
          </div>
        ) : (
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={`Ask ${selectedAgent}…`}
            disabled={streaming}
            className="h-9 min-w-0 flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 text-[13px] text-zinc-200 placeholder:text-zinc-600 outline-none transition-colors focus:border-cyan-400/40 focus:bg-white/[0.06] focus:ring-2 focus:ring-cyan-400/20 disabled:opacity-50"
          />
        )}
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
