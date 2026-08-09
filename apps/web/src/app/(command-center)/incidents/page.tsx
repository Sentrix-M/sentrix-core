"use client";

import { useEffect, useState } from "react";

import { AlertIcon } from "@/components/command-center/icons";
import { memoryApi, type FindingRecord } from "@/lib/api";

export default function IncidentsPage() {
  const [findings, setFindings] = useState<FindingRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    memoryApi
      .listFindings()
      .then((res) => {
        if (!cancelled) setFindings((res.items as FindingRecord[]) ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load findings.");
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
          <h1 className="text-lg font-semibold text-zinc-100">Incidents</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Recorded security findings and incidents across your estate</p>
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] py-16 text-center text-sm text-zinc-500">
          Loading incidents…
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      ) : findings.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
          <AlertIcon className="mb-3 h-10 w-10 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-400">No incidents recorded</p>
          <p className="mt-1 text-xs text-zinc-600">
            Security findings from the AI copilot will appear here.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {findings.map((finding) => (
            <div
              key={finding.id}
              className="flex flex-col gap-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="flex flex-col gap-1.5">
                <p className="text-sm font-medium text-zinc-100">
                  {finding.finding_type}
                  {finding.target ? (
                    <span className="ml-2 font-normal text-zinc-400">{finding.target}</span>
                  ) : null}
                </p>
                {finding.description ? (
                  <p className="text-sm text-zinc-400 line-clamp-2">{finding.description}</p>
                ) : null}
              </div>
              <span
                className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  finding.severity === "Critical"
                    ? "bg-red-500/10 text-red-400"
                    : finding.severity === "High"
                      ? "bg-orange-500/10 text-orange-400"
                      : finding.severity === "Medium"
                        ? "bg-amber-500/10 text-amber-400"
                        : "bg-zinc-500/10 text-zinc-400"
                }`}
              >
                {finding.severity}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
