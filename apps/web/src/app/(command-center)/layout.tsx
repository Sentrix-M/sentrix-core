"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { VoiceIcon } from "@/components/command-center/icons";
import { Sidebar } from "@/components/command-center/sidebar";
import { Topbar } from "@/components/command-center/topbar";
import { useAuth } from "@/lib/auth-context";

/**
 * Command Center shell — shared chrome for dashboard + AI Copilot.
 * Includes route guard (unauthenticated → /login), desktop sidebar,
 * mobile drawer, topbar, and floating Voice Orb.
 */
export default function CommandCenterLayout({ children }: { children: React.ReactNode }) {
  const { status, isAuthenticated } = useAuth();
  const router = useRouter();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Route guard: unauthenticated users are redirected to /login.
  useEffect(() => {
    if (status === "loading") return;
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [status, isAuthenticated, router]);

  // Show nothing while checking auth — avoids a flash of the protected UI.
  if (status === "loading" || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <div className="flex items-center gap-3 text-zinc-600">
          <span className="flex h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
          <span className="text-sm">Sentrix is loading…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-screen bg-zinc-950 text-zinc-100">
      {/* Ambient background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-zinc-950" />
        <div className="bg-grid absolute inset-0" />
        <div className="absolute -left-40 -top-40 h-[28rem] w-[28rem] rounded-full bg-indigo-600/20 blur-[120px]" />
        <div className="absolute -right-32 top-1/3 h-[26rem] w-[26rem] rounded-full bg-cyan-500/15 blur-[120px]" />
        <div className="absolute bottom-0 left-1/3 h-[24rem] w-[24rem] rounded-full bg-emerald-500/10 blur-[130px]" />
      </div>

      {/* Desktop sidebar */}
      <div className="sticky top-0 hidden h-screen shrink-0 lg:block">
        <Sidebar />
      </div>

      {/* Mobile drawer */}
      {mobileNavOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileNavOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 left-0 w-72 shadow-2xl">
            <Sidebar />
            <button
              type="button"
              onClick={() => setMobileNavOpen(false)}
              className="absolute right-3 top-4 flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-zinc-300"
              aria-label="Close navigation"
            >
              ✕
            </button>
          </div>
        </div>
      ) : null}

      {/* Main column */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        <Topbar
          title="Sentrix — AI Cybersecurity Copilot"
          subtitle="SOC Operations · Enterprise Grid"
          onMenuClick={() => setMobileNavOpen(true)}
        />
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>

{/* Floating Voice Orb — opens the AI Copilot voice experience.
          Navigates to /chat?voice=1 so the mounted AiChat auto-starts the
          existing Phase 16B voice flow (mic → WS/STT → submit → TTS). */}
      <button
        type="button"
        onClick={() => router.push("/chat?voice=1")}
        className="group fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-cyan-400 to-indigo-600 text-zinc-950 shadow-2xl shadow-cyan-500/30 ring-1 ring-white/40 transition-transform hover:scale-105"
        aria-label="Open voice assistant"
        title="Speak to the AI Copilot"
      >
        <span className="animate-pulse-ring absolute inset-0 rounded-full bg-cyan-400/40" />
        <VoiceIcon className="h-6 w-6 animate-flutter" />
        <span className="pointer-events-none absolute right-full mr-3 flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-medium text-zinc-200 opacity-0 ring-1 ring-inset ring-white/20 backdrop-blur transition-opacity duration-200 group-hover:opacity-100">
          <span className="text-cyan-300">●</span> Voice assistant
        </span>
      </button>
    </div>
  );
}
