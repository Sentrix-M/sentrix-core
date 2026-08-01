/**
 * @sentrix/ui
 *
 * Shared React components and design system primitives for the
 * Sentrix platform.
 */

import { cn } from "@sentrix/shared";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
}

export function Button({ variant = "primary", className, children, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium",
        "transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2",
        variant === "primary" && "bg-blue-600 text-white hover:bg-blue-700",
        variant === "secondary" && "bg-gray-200 text-gray-900 hover:bg-gray-300",
        variant === "ghost" && "bg-transparent text-gray-700 hover:bg-gray-100",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  children: ReactNode;
}

export function Card({ title, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn("rounded-lg border border-gray-200 bg-white p-6 shadow-sm", className)}
      {...rest}
    >
      {title ? <h3 className="mb-4 text-base font-semibold text-gray-900">{title}</h3> : null}
      {children}
    </div>
  );
}
