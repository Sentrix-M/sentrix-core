import {
  AlertIcon,
  CrosshairIcon,
  FileScanIcon,
  RadarIcon,
  ShieldIcon,
  SparklesIcon,
} from "@/components/command-center/icons";
import {
  AiStatus,
  Alerts,
  RecentConversations,
  SystemHealth,
  ToolStatus,
} from "@/components/command-center/widgets";
import { currentUser, kernelStatus, type QuickAction, quickActions } from "@/lib/mock-data";

const actionIcons: Record<QuickAction["icon"], typeof SparklesIcon> = {
  logs: RadarIcon,
  alerts: AlertIcon,
  hunt: CrosshairIcon,
  file: FileScanIcon,
  scan: ShieldIcon,
};

function QuickActionCard({ action }: { action: QuickAction }) {
  const Icon = actionIcons[action.icon];
  return (
    <button
      type="button"
      className="glass glass-hover group flex flex-col gap-2 rounded-2xl p-4 text-left"
    >
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400/90 to-indigo-600 text-zinc-950 shadow-lg shadow-cyan-500/10">
        <Icon className="h-4.5 w-4.5" />
      </div>
      <div>
        <p className="text-[13px] font-semibold text-zinc-100">{action.label}</p>
        <p className="mt-0.5 text-[11px] text-zinc-500">{action.description}</p>
      </div>
    </button>
  );
}

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-5">
      {/* Greeting banner */}
      <section className="glass relative overflow-hidden rounded-2xl p-6 sm:p-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-cyan-500/15 blur-[80px]" />
        <div className="pointer-events-none absolute -bottom-24 left-1/3 h-64 w-64 rounded-full bg-indigo-600/15 blur-[90px]" />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/10 px-2.5 py-1 text-[10px] font-medium text-emerald-300 ring-1 ring-inset ring-emerald-400/20">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                </span>
                {kernelStatus.state}
              </span>
            </div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-50 sm:text-3xl">
              Welcome back,{" "}
              <span className="bg-gradient-to-r from-cyan-300 to-indigo-300 bg-clip-text text-transparent">
                {currentUser.name.split(" ")[0]}
              </span>
            </h1>
            <p className="mt-1.5 text-sm text-zinc-400">
              <span className="font-semibold text-emerald-300">{kernelStatus.sinceLabel}</span> ·
              Kernel online for {kernelStatus.uptime} · {currentUser.title}
            </p>
          </div>

          <div className="shrink-0">
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-br from-cyan-400 to-indigo-600 px-5 py-2.5 text-sm font-semibold text-zinc-950 shadow-lg shadow-cyan-500/20 transition-all hover:brightness-110"
            >
              <SparklesIcon className="h-4 w-4" />
              Open AI Copilot
            </button>
          </div>
        </div>
      </section>

      {/* Quick actions */}
      <section>
        <h2 className="px-1 text-sm font-semibold text-zinc-100">Quick Actions</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {quickActions.map((action) => (
            <QuickActionCard key={action.id} action={action} />
          ))}
        </div>
      </section>

      {/* AI status + system health */}
      <section className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-1">
          <AiStatus />
        </div>
        <div className="xl:col-span-2">
          <SystemHealth />
        </div>
      </section>

      {/* Alerts + tools + conversations */}
      <section className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-1">
          <Alerts />
        </div>
        <div className="xl:col-span-2">
          <ToolStatus />
        </div>
      </section>

      <RecentConversations />
    </div>
  );
}
