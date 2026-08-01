"use client";

import { useId, type InputHTMLAttributes, type ReactNode } from "react";

type FieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
  hint?: string;
  rightSlot?: ReactNode;
};

/**
 * Labeled input field with built-in error and hint support.
 * `rightSlot` can be used for a "Show password" toggle or similar.
 */
export function Field({
  label,
  error,
  hint,
  rightSlot,
  id,
  className = "",
  ...inputProps
}: FieldProps) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  const errorId = error ? `${fieldId}-error` : undefined;
  const hintId = hint && !error ? `${fieldId}-hint` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <label
          htmlFor={fieldId}
          className="text-sm font-medium text-zinc-800 dark:text-zinc-200"
        >
          {label}
        </label>
        {rightSlot}
      </div>
      <input
        id={fieldId}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : hintId}
        className={`h-10 w-full rounded-lg border bg-white px-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none focus:ring-2 dark:bg-zinc-950 dark:text-zinc-100 ${
          error
            ? "border-red-500 focus:ring-red-500/40"
            : "border-zinc-300 focus:ring-zinc-900/20 dark:border-zinc-700"
        } ${className}`}
        {...inputProps}
      />
      {error ? (
        <p id={errorId} className="text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="text-xs text-zinc-500 dark:text-zinc-400">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

