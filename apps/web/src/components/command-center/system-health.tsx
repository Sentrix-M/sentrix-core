import { servicesHealth, systemMetrics } from "@/lib/mock-data";

const stateTone: Record<string, { dot: string; text: string; chip: string }> = {
  operational: {
    dot: "bg-emerald-400",
    text: "text-emerald-300",
    chip: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
  },
  degraded: {
    dot: "bg-amber-400",
    text: "text-amber-300",
    chip: "bg-amber-400/10 text-amber-300 ring-amber-400/20",
  },
  offline: {
    dot: "bg-red-400",
    text: "text-red-300",
    chip: "bg-red-400/10 text-red-300 ring-red-400/20",
  },
};

function MiniBars({ series }: { series: number[] }) {
  const max = Math.max(...series, 1);
  return (
    <div className="flex h-8 items-end gap-0.5" aria-hidden>
      {series.map((value, i) => {
        const h = Math.round((value / max) * 32);
        const last = i === series.length - 1;
        return (
          <span
            key={`${value}-${last ? "last" : "mid"}`}
            className={`w-full rounded-sm ${
              last ? "bg-gradient-to-t from-cyan-400/80 to-cyan-300" : "bg-white/[0.14]"
            }`}
            style={{ height: `${Math.max(h, 6)}%` }}
          />
        );
      })}
    </div>
  );
}

export function SystemHealth() {
  return (
    <section className="glass flex h-full flex-col rounded-2xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">System Health</h2>
          <p className="mt-0.5 text-[11px] text-zinc-500">Kernel + core services</p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 px-2.5 py-1 text-[10px] font-medium text-emerald-300 ring-1 ring-inset ring-emerald-400/20">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />5 / 6 operational
        </span>
      </div>

      {/* Metrics */}
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {systemMetrics.map((metric) => (
          <div
            key={metric.key}
            className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3"
          >
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] font-medium text-zinc-400">{metric.label}</span>
              <span className="font-mono text-[13px] font-semibold text-zinc-100">
                {metric.value}%
              </span>
            </div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.07]">
              <div
                className={`h-full rounded-full ${
                  metric.value > 85
                    ? "bg-gradient-to-r from-amber-400 to-red-500"
                    : metric.value > 70
                      ? "bg-gradient-to-r from-cyan-400 to-sky-500"
                      : "bg-gradient-to-r from-emerald-400 to-teal-500"
                }`}
                style={{ width: `${metric.value}%` }}
              />
            </div>
            <MiniBars series={metric.series} />
            <p className="mt-1 truncate font-mono text-[10px] text-zinc-500">{metric.usageLabel}</p>
          </div>
        ))}
      </div>

      {/* Services */}
      <div className="mt-4 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {servicesHealth.map((service) => {
          const tone = stateTone[service.state];
          return (
            <div
              key={service.name}
              className="flex items-center gap-2 rounded-lg border border-white/[0.04] bg-white/[0.02] px-2.5 py-2"
            >
              <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
              <span className="truncate text-[12px] text-zinc-300">{service.name}</span>
              <span
                className={`ml-auto rounded-full px-1.5 py-px text-[9px] font-medium uppercase tracking-wide ring-1 ring-inset ${tone.chip}`}
              >
                {service.state}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
