"use client";

import { AlertIcon, FilterIcon } from "@/components/command-center/icons";

export default function IncidentsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Incidents</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Active security incidents across your estate</p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-[11px] font-medium text-zinc-300 transition-colors hover:bg-white/[0.08]"
        >
          <FilterIcon className="h-3.5 w-3.5" />
          Filter
        </button>
      </div>

      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
        <AlertIcon className="mb-3 h-10 w-10 text-zinc-600" />
        <p className="text-sm font-medium text-zinc-400">Incident dashboard coming soon</p>
        <p className="mt-1 text-xs text-zinc-600">Real-time incident triage and response workflow</p>
      </div>
    </div>
  );
}
