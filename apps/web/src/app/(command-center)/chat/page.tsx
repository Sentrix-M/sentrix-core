import { AiChat } from "@/components/command-center/ai-chat";
import { AiStatus } from "@/components/command-center/ai-status";
import { RecentConversations } from "@/components/command-center/recent-conversations";

export default async function ChatPage({
  searchParams,
}: {
  searchParams: Promise<{ voice?: string }>;
}) {
  const params = await searchParams;
  const autoStartVoice = params.voice === "1";

  return (
    <div className="grid h-full min-h-[calc(100vh-4rem-3rem)] grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      {/* Main chat */}
      <div className="flex min-h-0 flex-col">
        <AiChat autoStartVoice={autoStartVoice} />
      </div>

      {/* Right rail */}
      <div className="flex flex-col gap-5">
        <AiStatus />
        <RecentConversations />
      </div>
    </div>
  );
}
