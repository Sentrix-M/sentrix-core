"use client";

import { BellIcon, LogoIcon, MenuIcon, SearchIcon } from "@/components/command-center/icons";
import { useAuth } from "@/lib/auth-context";
import { kernelStatus } from "@/lib/mock-data";

const alertCount = 7;

export function Topbar({
  title,
  subtitle,
  onMenuClick,
}: {
  title: string;
  subtitle: string;
  onMenuClick: () => void;
}) {
  const { user } = useAuth();

  const initials = user
    ? (() => {
        const parts = user.full_name.trim().split(/\s+/);
        return parts.length >= 2
          ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
          : parts[0]?.slice(0, 2).toUpperCase() ?? "?";
      })()
    : "?";

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-white/[0.06] bg-zinc-950/60 px-4 backdrop-blur-xl sm:px-6">
      {/* Mobile brand + menu */}
      <button
        type="button"
        onClick={onMenuClick}
        className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04] text-zinc-300 transition-colors hover:bg-white/[0.08] lg:hidden"
        aria-label="Toggle navigation"
      >
        <MenuIcon className="h-5 w-5" />
      </button>

      <div className="flex items-center gap-2 lg:hidden">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400/90 to-indigo-600 text-zinc-950">
          <LogoIcon className="h-4 w-4" strokeWidth={2.2} />
        </span>
        <span className="text-sm font-semibold tracking-[0.16em] text-zinc-100">SENTRIX</span>
      </div>

      {/* Page title */}
      <div className="hidden min-w-0 lg:block">
        <h1 className="truncate text-[15px] font-semibold text-zinc-100">{title}</h1>
        <p className="truncate text-[11px] text-zinc-500">{subtitle}</p>
      </div>

      {/* Search */}
      <div className="ml-2 hidden flex-1 items-center sm:flex md:max-w-md">
        <div className="group relative w-full">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="Search alerts, assets, IOCs…"
            className="h-9 w-full rounded-xl border border-white/[0.08] bg-white/[0.04] pl-9 pr-3 text-[13px] text-zinc-200 placeholder:text-zinc-500 outline-none transition-colors focus:border-cyan-400/40 focus:bg-white/[0.06] focus:ring-2 focus:ring-cyan-400/20"
          />
        </div>
      </div>

      <div className="ml-auto flex items-center gap-2">
        {/* Kernel pill */}
        <div className="hidden items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 md:flex">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <span className="text-[11px] font-medium text-emerald-300">{kernelStatus.state}</span>
          <span className="font-mono text-[10px] text-zinc-500">{kernelStatus.uptime}</span>
        </div>

        {/* Alerts */}
        <button
          type="button"
          className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.04] text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-zinc-200"
          aria-label={`Notifications, ${alertCount} new alerts`}
        >
          <BellIcon className="h-[18px] w-[18px]" />
          <span className="absolute -right-1 -top-1 inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold leading-none text-white ring-2 ring-zinc-950">
            {alertCount}
          </span>
        </button>

        {/* Avatar */}
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500/80 to-violet-600/80 text-[11px] font-bold text-white ring-1 ring-inset ring-white/20">
          {initials}
        </div>

        <div className="hidden text-left leading-tight xl:block">
          <p className="text-[13px] font-medium text-zinc-200">{user?.full_name ?? "User"}</p>
          <p className="text-[10px] text-zinc-500">{user?.email ?? ""}</p>
        </div>
      </div>
    </header>
  );
}
