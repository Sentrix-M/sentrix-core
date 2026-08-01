import {
  BrainIcon,
  ConnectionIcon,
  CpuIcon,
  DatabaseIcon,
  MemoryIcon,
  TargetIcon,
  VoiceIcon,
} from "@/components/command-center/icons";
import { activeModel, aiStatusItems } from "@/lib/mock-data";

const iconMap = {
  cpu: CpuIcon,
  memory: MemoryIcon,
  brain: BrainIcon,
  connection: ConnectionIcon,
  database: DatabaseIcon,
  voice: VoiceIcon,
  target: TargetIcon,
} as const;

const barTone: Record<string, { bar: string; ring: string; text: string; chip: string }> = {
  emerald: {
    bar: "from-emerald-400 to-teal-500",
    ring: "ring-emerald-400/20",
    text: "text-emerald-300",
    chip: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
  },
  cyan: {
    bar: "from-cyan-400 to-sky-500",
    ring: "ring-cyan-400/20",
    text: "text-cyan-300",
    chip: "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20",
  },
  violet: {
    bar: "from-violet-400 to-fuchsia-500",
    ring: "ring-violet-400/20",
    text: "text-violet-300",
    chip: "bg-violet-400/10 text-violet-300 ring-violet-400/20",
  },
};

export function AiStatus() {
  const kernel = aiStatusItems[0];
  const others = aiStatusItems.slice(1);

  return (
    <section className="glass flex h-full flex-col rounded-2xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">AI Status</h2>
          <p className="mt-0.5 text-[11px] text-zinc-500">Live inference telemetry</p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full bg-white/[0.06] px-2.5 py-1 text-[10px] font-medium text-zinc-300 ring-1 ring-inset ring-white/10">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </span>
          Live
        </span>
      </div>

      {/* Active model */}
      <div className="mt-4 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400/90 to-indigo-600 text-zinc-950">
            <BrainIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-zinc-100">{activeModel.name}</p>
            <p className="truncate text-[10px] uppercase tracking-wide text-zinc-500">
              {activeModel.provider}
            </p>
          </div>
          <span className="ml-auto font-mono text-[11px] text-cyan-300">{activeModel.latency}</span>
        </div>
      </div>

      {/* Primary kernel item */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-[13px]">
          <span className="flex items-center gap-2 text-zinc-200">
            <CpuIcon className="h-4 w-4 text-cyan-300" />
            {kernel.label}
          </span>
          <span className="font-mono text-sm font-semibold text-emerald-300">{kernel.value}%</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-teal-500"
            style={{ width: `${kernel.value}%` }}
          />
        </div>
        <p className="mt-1.5 text-[10px] text-zinc-500">{kernel.caption}</p>
      </div>

      {/* Remaining items */}
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 xl:grid-cols-2">
        {others.map((item) => {
          const tone = barTone[item.tone];
          const Icon = iconMap[item.icon];
          return (
            <div key={item.key} className="min-w-0">
              <div className="flex items-center justify-between">
                <span
                  className={`inline-flex items-center gap-1.5 text-[11px] font-medium ${tone.text}`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </span>
                <span className="font-mono text-[11px] font-semibold text-zinc-300">
                  {item.value}
                </span>
              </div>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.07]">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${tone.bar}`}
                  style={{ width: `${Math.min(item.value, 100)}%` }}
                />
              </div>
              <p className="mt-1 truncate text-[10px] text-zinc-500">{item.caption}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}
