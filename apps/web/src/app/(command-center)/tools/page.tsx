"use client";

import { useEffect, useState } from "react";

import { WrenchIcon } from "@/components/command-center/icons";
import { toolsApi, type ToolSummary } from "@/lib/api";

export default function ToolsPage() {
  const [tools, setTools] = useState<ToolSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    toolsApi
      .list()
      .then((res) => {
        if (!cancelled) setTools(res.tools ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load tools.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Tools</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Registered security tools available to the kernel</p>
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] py-16 text-center text-sm text-zinc-500">
          Loading tools…
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      ) : tools.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
          <WrenchIcon className="mb-3 h-10 w-10 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-400">No tools registered</p>
          <p className="mt-1 text-xs text-zinc-600">The tool registry is empty.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {tools.map((tool) => (
            <div
              key={tool.name}
              className="flex flex-col gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/[0.06] text-zinc-300">
                    <WrenchIcon className="h-4.5 w-4.5" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-zinc-100">{tool.name}</p>
                    <p className="text-xs text-zinc-500">v{tool.version}</p>
                  </div>
                </div>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    tool.enabled
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-zinc-500/10 text-zinc-500"
                  }`}
                >
                  {tool.enabled ? "Enabled" : "Disabled"}
                </span>
              </div>
              <p className="text-sm text-zinc-400">{tool.description}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
