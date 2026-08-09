/**
 * Sentrix web — typed API client for the FastAPI backend.
 *
 * Responsibilities:
 *  - Read the API base URL from `NEXT_PUBLIC_API_URL` (see `.env.example`).
 *  - Attach the bearer access token to outgoing requests when present.
 *  - On a 401, attempt a transparent refresh (single-flight) and retry the
 *    original request once. If refresh fails, clear the session.
 */

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  org_id: string;
  is_active: boolean;
  mfa_enabled: boolean;
  created_at: string;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

export type ApiError = {
  code: string;
  message: string;
  details?: unknown;
};

export type LoginInput = {
  email: string;
  password: string;
};

export type RegisterInput = {
  email: string;
  password: string;
  full_name: string;
};

export type ConversationMetadata = {
  model: string | null;
  reasoning: string[] | null;
  evidence: string[] | null;
  sources: string[] | null;
  tools_used: string[] | null;
  execution_time_ms: number | null;
};

export type ConversationMessageInput = {
  conversation_id: string;
  message: string;
};

export type ConversationMessageResponse = {
  conversation_id: string;
  response: string;
  timestamp: string;
  metadata: ConversationMetadata;
};

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

export type ToolSummary = {
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  input_schema?: Record<string, unknown> | null;
  output_schema?: Record<string, unknown> | null;
};

export type ToolListResponse = {
  tools: ToolSummary[];
  total: number;
};

export type ToolExecuteResponse = {
  success: boolean;
  tool: string;
  output: unknown;
  error: string | null;
  metadata: Record<string, unknown>;
};

// ---------------------------------------------------------------------------
// RAG / Knowledge
// ---------------------------------------------------------------------------

export type RagDocument = {
  id: string;
  filename: string;
  page_count: number;
  total_chunks: number;
  uploaded_at: string;
};

export type RagDocumentListResponse = {
  documents: RagDocument[];
  total: number;
};

export type RagSearchResult = {
  chunk_id: string;
  document_id: string;
  text: string;
  filename: string;
  page_number: number;
  chunk_index: number;
  score: number;
};

export type RagSearchResponse = {
  query: string;
  results: RagSearchResult[];
  total: number;
};

// ---------------------------------------------------------------------------
// Long-Term Memory (reports / investigations)
// ---------------------------------------------------------------------------

export type ReportRecord = {
  id: string;
  org_id: string;
  user_id: string;
  created_at: string;
  title: string;
  report_format: string;
  severity: string;
  summary: string;
  payload: Record<string, unknown>;
};

export type InvestigationRecord = {
  id: string;
  org_id: string;
  user_id: string;
  created_at: string;
  title: string;
  target: string;
  summary: string;
  findings: Record<string, unknown>[];
};

export type FindingRecord = {
  id: string;
  org_id: string;
  user_id: string;
  created_at: string;
  finding_type: string;
  target: string;
  severity: string;
  description: string;
  detail: Record<string, unknown>;
};

export type MemoryListResponse = {
  items: ReportRecord[] | InvestigationRecord[] | FindingRecord[];
  total: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Token storage helpers (localStorage so sessions survive reloads).
// ---------------------------------------------------------------------------

const ACCESS_TOKEN_KEY = "sentrix.access_token";
const REFRESH_TOKEN_KEY = "sentrix.refresh_token";

let _accessToken: string | null = null;
let _refreshToken: string | null = null;

function readStorage() {
  if (typeof window === "undefined") return;
  _accessToken = window.localStorage.getItem(ACCESS_TOKEN_KEY);
  _refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

/** Attach tokens stored in memory/token storage (init at module load). */
if (typeof window !== "undefined") {
  readStorage();
}

export function getAccessToken(): string | null {
  if (typeof window !== "undefined" && _accessToken === null) readStorage();
  return _accessToken;
}

export function getRefreshToken(): string | null {
  if (typeof window !== "undefined" && _refreshToken === null) readStorage();
  return _refreshToken;
}

export function setTokens(access: string, refresh: string) {
  _accessToken = access;
  _refreshToken = refresh;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, access);
    window.localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  }
}

export function clearTokens() {
  _accessToken = null;
  _refreshToken = null;
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

// ---------------------------------------------------------------------------
// Request helper
// ---------------------------------------------------------------------------

function normalizeError(payload: unknown): ApiError {
  if (payload && typeof payload === "object") {
    const maybe = payload as { error?: { code?: string; message?: string } };
    if (maybe.error) {
      return {
        code: maybe.error.code ?? "unknown",
        message: maybe.error.message ?? "An unexpected error occurred.",
      };
    }
  }
  return { code: "unknown", message: "An unexpected error occurred." };
}

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refresh = getRefreshToken();
  if (!refresh) throw new Error("No refresh token available.");

  const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });

  if (!res.ok) {
    clearTokens();
    throw new Error("Session expired. Please sign in again.");
  }

  const body = (await res.json()) as TokenPair;
  setTokens(body.access_token, body.refresh_token);
  return body.access_token;
}

/**
 * Perform an authenticated JSON request.
 *
 * On a 401, refreshes the session once and retries. A `logout` callback can
 * be provided (wired by the auth context) so the UI can react to an expired
 * session.
 */
export async function api<T>(
  path: string,
  init: RequestInit & { skipRefresh?: boolean } = {},
  onAuthFailure?: () => void,
): Promise<T> {
  const { skipRefresh = false, ...options } = init;
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401 && !skipRefresh && getRefreshToken()) {
    try {
      refreshPromise ??= refreshAccessToken();
      const newToken = await refreshPromise;
      refreshPromise = null;

      headers.set("Authorization", `Bearer ${newToken}`);
      res = await fetch(`${API_URL}${path}`, { ...options, headers });
    } catch {
      refreshPromise = null;
      onAuthFailure?.();
      throw new Error("Session expired. Please sign in again.");
    }
  }

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // Non-JSON error response; fall through to generic handling.
    }
    throw new Error(normalizeError(body).message);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Auth endpoint functions
// ---------------------------------------------------------------------------

export const authApi = {
  login(input: LoginInput) {
    return api<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
      skipRefresh: true,
    });
  },

  register(input: RegisterInput) {
    return api<TokenPair>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify(input),
      skipRefresh: true,
    });
  },

  me() {
    return api<User>("/api/v1/auth/me", {}, () => {
      clearTokens();
    });
  },

  logout(refreshToken: string) {
    return api<void>("/api/v1/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipRefresh: true,
    });
  },

  forgotPassword(email: string) {
    // NOTE: The backend forgot-password endpoint is stubbed (no SMTP
    // provider configured). This call documents the intended contract and
    // returns a success immediately for the current scope.
    return Promise.resolve({ message: "If that email exists, a reset link was sent." });
  },
};

// ---------------------------------------------------------------------------
// Conversation endpoint functions
// ---------------------------------------------------------------------------

export type StreamEventType = "status" | "token" | "completed" | "error" | "done";

export type StreamStatusPayload = { status: string; detail?: string; at: string };
export type StreamTokenPayload = { token: string };
export type StreamCompletedPayload = {
  provider: string;
  model: string | null;
  content: string;
  execution_time_ms: number;
  at: string;
};
export type StreamErrorPayload = { message: string; at: string };

export type StreamEvent = {
  event: StreamEventType;
  data: StreamStatusPayload | StreamTokenPayload | StreamCompletedPayload | StreamErrorPayload | Record<string, never>;
};

export const conversationApi = {
  sendMessage(input: ConversationMessageInput) {
    return api<ConversationMessageResponse>("/api/v1/conversations/message", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /**
   * Stream an AI response via Server-Sent Events.
   *
   * Uses a raw `EventSource`-compatible fetch POST (EventSource only supports
   * GET), so we read the `text/event-stream` body incrementally and dispatch
   * parsed events to `onEvent`. Returns an abort handle so the caller can Stop.
   */
  streamMessage(
    input: ConversationMessageInput,
    onEvent: (event: StreamEvent) => void,
    onError: (message: string) => void,
    onFinally?: () => void,
  ) {
    const controller = new AbortController();
    const token = getAccessToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/conversations/stream`, {
          method: "POST",
          headers,
          body: JSON.stringify(input),
          signal: controller.signal,
        });

        if (!res.ok || !res.body) {
          try {
            const body = (await res.json()) as unknown;
            onError(normalizeError(body).message);
          } catch {
            onError(`Stream request failed with status ${res.status}.`);
          }
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        const dispatch = (raw: string) => {
          let event = "message";
          const dataLines: string[] = [];
          for (const line of raw.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          if (!dataLines.length) return;
          const dataText = dataLines.join("\n");
          try {
            const data = JSON.parse(dataText) as StreamEvent["data"];
            onEvent({ event: (event as StreamEventType) || "message", data });
          } catch {
            // Ignore malformed payloads; keep the stream alive.
          }
        };

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split("\n\n");
          buffer = blocks.pop() ?? "";
          for (const block of blocks) {
            if (block.trim()) dispatch(block);
          }
        }

        // Flush any remaining block (e.g. final done event without trailing blank).
        if (buffer.trim()) dispatch(buffer);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // Caller pressed Stop; the stream was intentionally aborted.
          return;
        }
        const message = err instanceof Error ? err.message : "Failed to reach the AI engine.";
        onError(message);
      } finally {
        onFinally?.();
      }
    })();

return {
      abort: () => controller.abort(),
      promise: undefined as Promise<void> | undefined,
    };
  },
};

// ---------------------------------------------------------------------------
// Tools endpoint functions
// ---------------------------------------------------------------------------

export const toolsApi = {
  list() {
    return api<ToolListResponse>("/api/v1/tools");
  },

  execute(tool: string, input: Record<string, unknown>, timeout?: number) {
    return api<ToolExecuteResponse>("/api/v1/tools/execute", {
      method: "POST",
      body: JSON.stringify({ tool, input, timeout }),
    });
  },
};

// ---------------------------------------------------------------------------
// RAG / Knowledge endpoint functions
// ---------------------------------------------------------------------------

export const ragApi = {
  listDocuments() {
    return api<RagDocumentListResponse>("/api/v1/rag/documents");
  },

  search(query: string, topK = 5) {
    return api<RagSearchResponse>("/api/v1/rag/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k: topK }),
    });
  },
};

// ---------------------------------------------------------------------------
// Long-Term Memory endpoint functions (reports / investigations)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Text-to-Speech endpoint functions (voice output)
// ---------------------------------------------------------------------------

export const ttsApi = {
  /**
   * Synthesize speech from a completed assistant message.
   *
   * Returns raw audio bytes which the caller decodes into a playable blob.
   * The browser always routes through this endpoint (never a provider
   * directly), so Mock/Kokoro/OpenAI/ElevenLabs/Piper all stay behind one API.
   */
  async synthesize(text: string): Promise<Blob> {
    const token = getAccessToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_URL}/api/v1/tts/synthesize`, {
      method: "POST",
      headers,
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        // Non-JSON error; fall through to generic handling.
      }
      throw new Error(normalizeError(body).message);
    }
    return res.blob();
  },
};

export const memoryApi = {
  listReports(userId?: string, limit = 50) {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    params.set("limit", String(limit));
    return api<MemoryListResponse>(`/api/v1/memory/reports?${params.toString()}`);
  },

listInvestigations(userId?: string, limit = 50) {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    params.set("limit", String(limit));
    return api<MemoryListResponse>(`/api/v1/memory/investigations?${params.toString()}`);
  },

  listFindings(userId?: string, limit = 50) {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    params.set("limit", String(limit));
    return api<MemoryListResponse>(`/api/v1/memory/findings?${params.toString()}`);
  },
};

