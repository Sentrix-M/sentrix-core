"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type SubmitButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  loadingText?: string;
  children: ReactNode;
};

/**
 * Accessible submit button with a loading state that simultaneously
 * disables the button and announces progress to assistive tech.
 */
export function SubmitButton({
  loading = false,
  loadingText = "Please wait…",
  children,
  disabled,
  className = "",
  ...rest
}: SubmitButtonProps) {
  return (
    <button
      type="submit"
      disabled={disabled || loading}
      aria-busy={loading}
      className={`inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-zinc-900 text-sm font-semibold text-white transition-colors hover:bg-zinc-700 focus:outline-none focus:ring-2 focus:ring-zinc-900/30 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300 ${className}`}
      {...rest}
    >
      {loading ? (
        <>
          <span
            aria-hidden
            className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-400 border-t-transparent"
          />
          {loadingText}
        </>
      ) : (
        children
      )}
    </button>
  );
}
