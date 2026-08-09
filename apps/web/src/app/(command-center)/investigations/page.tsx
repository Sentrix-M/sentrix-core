"use client";

import { useEffect, useState } from "react";

import { ScrollIcon } from "@/components/command-center/icons";
import { memoryApi, type InvestigationRecord } from "@/lib/api";

export default function InvestigationsPage() {
  const [investigations, setInvestigations] = useState<InvestigationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    memoryApi
      .listInvestigations()
      .then((res) => {
        if (!cancelled) setInvestigations((res.items as InvestigationRecord[]) ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load investigations.");
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
          <h1 className="text-lg font-semibold text-zinc-100">Investigations</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Recorded security investigations</p>
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] py-16 text-center text-sm text-zinc-500">
          Loading investigations…
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      ) : investigations.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
          <ScrollIcon className="mb-3 h-10 w-10 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-400">No investigations yet</p>
          <p className="mt-1 text-xs text-zinc-600">
            Run an investigation from the AI copilot to have it recorded here.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {investigations.map((record) => (
            <div
              key={record.id}
              className="flex flex-col gap-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5"
            >
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-zinc-100">{record.title}</p>
              </div>
              {record.target ? (
                <p className="text-xs font-medium text-zinc-500">
                  Target: <span className="text-zinc-300">{record.target}</span>
                </p>
              ) : null}
              {record.summary ? (
                <p className="text-sm text-zinc-400 line-clamp-3">{record.summary}</p>
              ) : null}
              {record.findings.length > 0 ? (
                <p className="text-xs text-zinc-500">{record.findings.length} finding(s)</p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
