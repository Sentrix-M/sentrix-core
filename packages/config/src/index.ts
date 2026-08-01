/**
 * @sentrix/config
 *
 * Shared configuration and environment validation for the
 * Sentrix platform. Uses Zod to define and enforce a consistent
 * environment contract across all clients and packages.
 */

import { z } from "zod";

/** Zod schema describing the shared environment contract. */
export const envSchema = z.object({
  NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
  API_BASE_URL: z.url().default("http://localhost:8000"),
  PUBLIC_APP_NAME: z.string().default("Sentrix"),
});

/** Type-safe environment configuration derived from the schema. */
export type EnvConfig = z.infer<typeof envSchema>;

/** Environment variable source. */
type EnvSource = NodeJS.ProcessEnv;

/**
 * Validate and parse a raw environment object into a typed config.
 * Throws a Zod error when required variables are missing or invalid.
 */
export function loadEnvConfig(env: EnvSource = process.env): EnvConfig {
  return envSchema.parse(env);
}

/**
 * Safe variant of {@link loadEnvConfig}; returns `null` instead of
 * throwing when validation fails.
 */
export function tryLoadEnvConfig(env: EnvSource = process.env): EnvConfig | null {
  const result = envSchema.safeParse(env);
  return result.success ? result.data : null;
}
