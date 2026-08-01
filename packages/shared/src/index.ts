/**
 * @sentrix/shared
 *
 * Common utilities, constants, and helper functions shared across
 * the Sentrix platform (web, desktop, packages).
 */

/** Platform-wide application name. */
export const APP_NAME = "Sentrix";

/** Semantic version of the shared package. */
export const APP_VERSION = "0.1.0";

/** Returns true when running in a development environment. */
export function isDev(): boolean {
  return process.env.NODE_ENV !== "production";
}

/** Resolves after the given number of milliseconds. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Joins truthy class names, filtering out falsy values. */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
