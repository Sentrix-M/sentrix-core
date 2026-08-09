"use client";

import { PlugIcon } from "@/components/command-center/icons";

export default function IntegrationsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">Integrations</h1>
          <p className="mt-0.5 text-sm text-zinc-500">Connect your security stack to Sentrix</p>
        </div>
      </div>

      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/10 bg-white/[0.02] py-20">
        <PlugIcon className="mb-3 h-10 w-10 text-zinc-600" />
        <p className="text-sm font-medium text-zinc-400">Integrations coming soon</p>
        <p className="mt-1 text-xs text-zinc-600">Wazuh, Suricata, Zeek, Splunk, Elastic, and more</p>
      </div>
    </div>
  );
}
