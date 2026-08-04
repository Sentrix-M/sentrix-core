"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-context";

export default function Home() {
  const { status, isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "loading") return;
    if (isAuthenticated) {
      router.replace("/dashboard");
    } else {
      router.replace("/login");
    }
  }, [status, isAuthenticated, router]);

  // Show nothing while deciding where to go — avoids a flash of the wrong page.
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950">
      <div className="flex items-center gap-3 text-zinc-600">
        <span className="flex h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
        <span className="text-sm">Sentrix is loading…</span>
      </div>
    </div>
  );
}
