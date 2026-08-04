"use client";

import { BookIcon } from "@/components/command-center/icons";

export default function KnowledgePage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Knowledge</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Cybersecurity knowledge base and MITRE ATT&CK mapping</p>
        </div>
      </div>

      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
        <BookIcon className="mb-3 h-10 w-10 text-zinc-600" />
        <p className="text-sm font-medium text-zinc-400">Knowledge base coming soon</p>
        <p className="mt-1 text-xs text-zinc-600">Techniques, procedures, and threat intelligence library</p>
      </div>
    </div>
  );
}
