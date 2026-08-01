"use client";

import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth-context";

/**
 * Client-side providers for the Sentrix web application.
 * Wrapped in the root layout so the auth session is available app-wide.
 */
export function Providers({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
