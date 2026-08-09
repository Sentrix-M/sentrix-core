"use client";

import { useEffect, useState } from "react";

import { ReportIcon } from "@/components/command-center/icons";
import { memoryApi, type ReportRecord } from "@/lib/api";

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    memoryApi
      .listReports()
      .then((res) => {
        if (!cancelled) setReports((res.items as ReportRecord[]) ?? []);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load reports.");
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
          <h1 className="text-lg font-semibold text-zinc-100">Reports</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Generated security incident reports</p>
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.02] py-16 text-center text-sm text-zinc-500">
          Loading reports…
        </div>
      ) : error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      ) : reports.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
          <ReportIcon className="mb-3 h-10 w-10 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-400">No reports yet</p>
          <p className="mt-1 text-xs text-zinc-600">
            Generate a report from the AI copilot to have it listed here.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {reports.map((report) => (
            <div
              key={report.id}
              className="flex flex-col gap-2 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="flex flex-col gap-1.5">
                <p className="text-sm font-medium text-zinc-100">{report.title}</p>
                {report.summary ? (
                  <p className="text-sm text-zinc-400 line-clamp-2">{report.summary}</p>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    report.severity === "Critical"
                      ? "bg-red-500/10 text-red-400"
                      : report.severity === "High"
                        ? "bg-orange-500/10 text-orange-400"
                        : report.severity === "Medium"
                          ? "bg-amber-500/10 text-amber-400"
                          : "bg-zinc-500/10 text-zinc-400"
                  }`}
                >
                  {report.severity}
                </span>
                <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[11px] font-medium text-zinc-400">
                  {report.report_format}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
