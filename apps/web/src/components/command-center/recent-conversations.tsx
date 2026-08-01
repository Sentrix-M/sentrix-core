import { ArrowUpRightIcon, ClockIcon, SparklesIcon } from "@/components/command-center/icons";
import { conversations } from "@/lib/mock-data";

export function RecentConversations() {
  return (
    <section className="glass flex h-full flex-col rounded-2xl p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">Recent Conversations</h2>
          <p className="mt-0.5 text-[11px] text-zinc-500">
            Continue where you left off with AI Copilot
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-full bg-white/[0.05] px-2.5 py-1 text-[10px] font-medium text-zinc-300 ring-1 ring-inset ring-white/10 transition-colors hover:bg-white/[0.1]"
        >
          View history
          <ArrowUpRightIcon className="h-3 w-3" />
        </button>
      </div>

      <div className="mt-4 flex flex-col gap-1.5">
        {conversations.slice(0, 4).map((conv) => (
          <button
            key={conv.id}
            type="button"
            className="group flex items-start gap-3 rounded-xl border border-white/[0.04] bg-white/[0.02] p-3 text-left transition-colors hover:border-white/[0.1] hover:bg-white/[0.04]"
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-400/20 to-indigo-500/20 text-cyan-300 ring-1 ring-inset ring-cyan-400/20">
              <SparklesIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="truncate text-[13px] font-medium text-zinc-200">{conv.title}</p>
                {conv.pinned ? (
                  <span className="rounded bg-cyan-400/10 px-1 py-px text-[9px] font-semibold uppercase tracking-wide text-cyan-300">
                    Pinned
                  </span>
                ) : null}
              </div>
              <p className="mt-0.5 truncate text-[11px] text-zinc-500">{conv.preview}</p>
              <div className="mt-1.5 flex items-center gap-2 text-[10px] text-zinc-600">
                <span className="inline-flex items-center gap-1">
                  <ClockIcon className="h-3 w-3" />
                  {conv.time} ago
                </span>
                <span className="h-0.5 w-0.5 rounded-full bg-zinc-700" />
                <span>{conv.agent}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
