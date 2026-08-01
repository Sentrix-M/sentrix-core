import { AiChat } from "@/components/command-center/ai-chat";
import { AiStatus } from "@/components/command-center/ai-status";
import { RecentConversations } from "@/components/command-center/recent-conversations";

export default function ChatPage() {
  return (
    <div className="grid h-full min-h-[calc(100vh-4rem-3rem)] grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      {/* Main chat */}
      <div className="flex min-h-0 flex-col">
        <AiChat />
      </div>

      {/* Right rail */}
      <div className="flex flex-col gap-5">
        <AiStatus />
        <RecentConversations />
      </div>
    </div>
  );
}
