import { AlertIcon, ChevronRightIcon } from "@/components/command-center/icons";
import { alerts, type Severity } from "@/lib/mock-data";

const severityTone: Record<Severity, { bar: string; chip: string; text: string; dot: string }> = {
  critical: {
    bar: "bg-red-500",
    chip: "bg-red-500/10 text-red-300 ring-red-400/30",
    text: "text-red-300",
    dot: "bg-red-400",
  },
  high: {
    bar: "bg-amber-500",
    chip: "bg-amber-500/10 text-amber-300 ring-amber-400/30",
    text: "text-amber-300",
    dot: "bg-amber-400",
  },
  medium: {
    bar: "bg-sky-500",
    chip: "bg-sky-500/10 text-sky-300 ring-sky-400/30",
    text: "text-sky-300",
    dot: "bg-sky-400",
  },
  low: {
    bar: "bg-zinc-500",
    chip: "bg-white/[0.06] text-zinc-400 ring-white/10",
    text: "text-zinc-400",
    dot: "bg-zinc-500",
  },
};

export function Alerts() {
  return (
    <section className="glass flex h-full flex-col rounded-2xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Alerts</h2>
          <p className="mt-0.5 text-[11px] text-zinc-500">Latest detections from active sensors</p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-full bg-white/[0.05] px-2.5 py-1 text-[10px] font-medium text-zinc-300 ring-1 ring-inset ring-white/10 transition-colors hover:bg-white/[0.1]"
        >
          View all
          <ChevronRightIcon className="h-3 w-3" />
        </button>
      </div>

      <div className="mt-3 flex flex-col gap-1.5">
        {alerts.map((alert) => {
          const tone = severityTone[alert.severity];
          return (
            <div
              key={alert.id}
              className="group flex items-start gap-3 rounded-xl border border-white/[0.04] bg-white/[0.02] p-3 transition-colors hover:border-white/[0.1] hover:bg-white/[0.04]"
            >
              <span className={`mt-0.5 w-1 self-stretch rounded-full ${tone.bar}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide ring-1 ring-inset ${tone.chip}`}
                  >
                    <span className={`h-1 w-1 rounded-full ${tone.dot}`} />
                    {alert.severity}
                  </span>
                  <span className="text-[10px] text-zinc-500">{alert.time}</span>
                  <span className="ml-auto truncate font-mono text-[10px] text-zinc-600">
                    {alert.agent}
                  </span>
                </div>
                <p className="mt-1 truncate text-[13px] font-medium text-zinc-200">{alert.title}</p>
                <p className={`mt-0.5 text-[11px] ${tone.text}`}>{alert.source}</p>
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
          <AlertIcon className="h-3.5 w-3.5" />
          Open alert queue
        </button>
      </div>
    </section>
  );
}
