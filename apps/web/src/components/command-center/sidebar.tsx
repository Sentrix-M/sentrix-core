"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import {
  BookIcon,
  CrosshairIcon,
  GearIcon,
  GridIcon,
  LogoIcon,
  PlugIcon,
  RadarIcon,
  ReportIcon,
  ScrollIcon,
  SparklesIcon,
  WrenchIcon,
} from "@/components/command-center/icons";
import { useAuth } from "@/lib/auth-context";
import { kernelStatus } from "@/lib/mock-data";

type NavItem = {
  href: string;
  label: string;
  icon: typeof GridIcon;
};

const primaryNav: NavItem[] = [
  { href: "/dashboard", label: "Command Center", icon: GridIcon },
  { href: "/chat", label: "AI Copilot", icon: SparklesIcon },
  { href: "/incidents", label: "Incidents", icon: RadarIcon },
  { href: "/investigations", label: "Investigations", icon: ScrollIcon },
  { href: "/threat-hunting", label: "Threat Hunting", icon: CrosshairIcon },
  { href: "/knowledge", label: "Knowledge", icon: BookIcon },
  { href: "/tools", label: "Tools", icon: WrenchIcon },
  { href: "/integrations", label: "Integrations", icon: PlugIcon },
  { href: "/reports", label: "Reports", icon: ReportIcon },
  { href: "/settings", label: "Settings", icon: GearIcon },
];

const coreAgents = [
  { name: "SOC Agent", load: 72, tone: "emerald" },
  { name: "Threat Hunt", load: 45, tone: "cyan" },
  { name: "Malware Agent", load: 30, tone: "violet" },
  { name: "OSINT", load: 12, tone: "zinc" },
];

const usage = {
  pct: 68,
  label: "Daily operations",
  quota: "1.4 / 2.0 TUs",
};

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();

  const initials = user
    ? (() => {
        const parts = user.full_name.trim().split(/\s+/);
        return parts.length >= 2
          ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
          : parts[0]?.slice(0, 2).toUpperCase() ?? "?";
      })()
    : "?";

  return (
    <aside className="flex h-full w-72 flex-col border-r border-white/[0.06] bg-zinc-950/70 backdrop-blur-2xl">
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400/90 to-indigo-600 text-zinc-950 shadow-lg shadow-cyan-500/20">
          <LogoIcon className="h-5.5 w-5.5" strokeWidth={2} />
        </div>
        <div className="leading-tight">
          <div className="flex items-baseline gap-1.5">
            <span className="text-sm font-semibold tracking-[0.18em] text-zinc-100">SENTRIX</span>
            <span className="rounded bg-white/10 px-1 py-px text-[9px] font-bold uppercase tracking-wider text-zinc-300">
              Core
            </span>
          </div>
          <span className="text-[10px] uppercase tracking-widest text-zinc-500">
            Security Copilot
          </span>
        </div>
      </div>

      {/* Kernel status strip */}
      <div className="mx-4 mb-2 rounded-xl border border-white/[0.06] bg-white/[0.03] px-3 py-2.5">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <span className="text-xs font-medium text-emerald-300">{kernelStatus.state}</span>
          <span className="ml-auto font-mono text-[10px] text-zinc-500">
            {kernelStatus.version}
          </span>
        </div>
      </div>

      {/* Primary nav */}
      <nav className="scroll-thin flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
        <p className="px-2 pb-1.5 pt-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-600">
          Workspace
        </p>
        {primaryNav.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={`group flex items-center gap-3 rounded-xl px-2.5 py-2 text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-white/[0.08] text-zinc-50 shadow-inner ring-1 ring-inset ring-white/[0.08]"
                  : "text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200"
              }`}
            >
              <Icon
                className={`h-[18px] w-[18px] transition-colors ${
                  isActive ? "text-cyan-300" : "text-zinc-500 group-hover:text-zinc-300"
                }`}
              />
              {item.label}
              {item.label === "Incidents" ? (
                <span className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500/15 px-1.5 text-[10px] font-bold text-red-300 ring-1 ring-inset ring-red-400/30">
                  7
                </span>
              ) : null}
              {item.label === "Threat Hunting" ? (
                <span className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500/15 px-1.5 text-[10px] font-bold text-amber-300 ring-1 ring-inset ring-amber-400/30">
                  3
                </span>
              ) : null}
            </Link>
          );
        })}

        {/* Active agents */}
        <p className="px-2 pb-1.5 pt-5 text-[10px] font-semibold uppercase tracking-[0.16em] text-zinc-600">
          Active agents
        </p>
        {coreAgents.map((agent) => (
          <div
            key={agent.name}
            className="flex items-center gap-2.5 rounded-xl px-2.5 py-1.5 text-[12px] text-zinc-400"
          >
            <span className="relative flex h-4 w-4 items-center justify-center">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  agent.tone === "emerald"
                    ? "bg-emerald-400"
                    : agent.tone === "cyan"
                      ? "bg-cyan-400"
                      : agent.tone === "violet"
                        ? "bg-violet-400"
                        : "bg-zinc-500"
                }`}
              />
            </span>
            <span className="truncate">{agent.name}</span>
            <span className="ml-auto font-mono text-[10px] text-zinc-600">{agent.load}%</span>
          </div>
        ))}
      </nav>

      {/* Usage meter */}
      <div className="mx-4 mb-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-zinc-400">Subscription</span>
          <span className="font-mono text-zinc-500">{usage.quota}</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.08]">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-indigo-500"
            style={{ width: `${usage.pct}%` }}
          />
        </div>
        <p className="mt-1.5 text-[10px] text-zinc-600">{usage.label}</p>
      </div>

      {/* User */}
      <div className="border-t border-white/[0.06] p-3">
        <div className="flex items-center gap-3 rounded-xl px-2 py-1.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500/80 to-violet-600/80 text-[11px] font-bold text-white">
            {initials}
          </div>
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-[13px] font-medium text-zinc-200">{user?.full_name ?? "User"}</p>
            <p className="truncate text-[10px] text-zinc-500">{user?.email ?? ""}</p>
          </div>
          <button
            type="button"
            onClick={() => {
              logout();
              router.push("/login");
            }}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/[0.08] bg-white/[0.04] text-[10px] text-zinc-500 transition-colors hover:border-red-400/30 hover:bg-red-500/10 hover:text-red-300"
            aria-label="Sign out"
            title="Sign out"
          >
            ←
          </button>
        </div>
      </div>
    </aside>
  );
}
