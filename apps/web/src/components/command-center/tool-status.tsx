import { ConnectionIcon, WrenchIcon } from "@/components/command-center/icons";
import { type ToolStatus as ToolStatusValue, tools } from "@/lib/mock-data";

const countByStatus = tools.reduce<Record<string, number>>((acc, tool) => {
  acc[tool.status] = (acc[tool.status] ?? 0) + 1;
  return acc;
}, {});

const statusTone: Record<ToolStatusValue, { dot: string; chip: string; label: string }> = {
  online: {
    dot: "bg-emerald-400",
    chip: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
    label: "Online",
  },
  busy: {
    dot: "bg-cyan-400",
    chip: "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20",
    label: "Busy",
  },
  degraded: {
    dot: "bg-amber-400",
    chip: "bg-amber-400/10 text-amber-300 ring-amber-400/20",
    label: "Degraded",
  },
  offline: {
    dot: "bg-red-400",
    chip: "bg-red-400/10 text-red-300 ring-red-400/20",
    label: "Offline",
  },
};

export function ToolStatus() {
  return (
    <section className="glass flex h-full flex-col rounded-2xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Tool Status</h2>
          <p className="mt-0.5 text-[11px] text-zinc-500">Security toolkit availability</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-400/10 px-2.5 py-1 text-[10px] font-medium text-cyan-300 ring-1 ring-inset ring-cyan-400/20">
          <ConnectionIcon className="h-3 w-3" />
          {countByStatus.online ?? 0} connected
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
        {tools.map((tool) => {
          const tone = statusTone[tool.status];
          return (
            <div
              key={tool.id}
              className="group rounded-xl border border-white/[0.05] bg-white/[0.02] p-3 transition-colors hover:border-white/[0.1] hover:bg-white/[0.04]"
            >
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-semibold text-zinc-200">{tool.name}</span>
                <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
              </div>
              <p className="mt-0.5 truncate text-[10px] text-zinc-500">{tool.kind}</p>
              <div className="mt-2.5 flex items-center justify-between">
                <span
                  className={`rounded-full px-1.5 py-px text-[9px] font-medium uppercase tracking-wide ring-1 ring-inset ${tone.chip}`}
                >
                  {tone.label}
                </span>
                <span className="font-mono text-[9px] text-zinc-600">v{tool.version}</span>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.07]">
                <div
                  className={`h-full rounded-full ${
                    tool.status === "offline"
                      ? "bg-zinc-600"
                      : tool.load > 75
                        ? "bg-gradient-to-r from-amber-400 to-red-500"
                        : "bg-gradient-to-r from-cyan-400 to-indigo-500"
                  }`}
                  style={{
                    width: `${tool.status === "offline" ? 0 : Math.min(tool.load, 100)}%`,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-auto pt-3">
        <button
          type="button"
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-white/10 bg-white/[0.02] py-2 text-[11px] text-zinc-500 transition-colors hover:bg-white/[0.05] hover:text-zinc-300"
        >
          <WrenchIcon className="h-3.5 w-3.5" />
          Manage toolkit
        </button>
      </div>
    </section>
  );
}
