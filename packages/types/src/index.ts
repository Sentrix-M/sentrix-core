/**
 * @sentrix/types
 *
 * Shared TypeScript types and API interfaces used across the
 * Sentrix platform.
 */

/** Health-check response contract for API services. */
export interface HealthStatus {
  status: "ok" | "degraded" | "down";
  service: string;
  version: string;
}

/** Generic pagination wrapper used by list endpoints. */
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

/** Generic API envelope for consistent client/server contracts. */
export interface ApiResponse<T> {
  data: T;
  success: true;
  timestamp: string;
}

/** Result shape produced by the AI pipeline. */
export interface AiResult {
  agent: string;
  output: string;
  model: string;
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
}
