"use client";

import { ReportIcon } from "@/components/command-center/icons";

export default function ReportsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Reports</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Generate and schedule security reports</p>
        </div>
      </div>

      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
        <ReportIcon className="mb-3 h-10 w-10 text-zinc-600" />
        <p className="text-sm font-medium text-zinc-400">Reports coming soon</p>
        <p className="mt-1 text-xs text-zinc-600">Executive summaries, compliance reports, and SOC metrics</p>
      </div>
    </div>
  );
}
