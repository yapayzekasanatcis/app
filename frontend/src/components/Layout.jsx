import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import NovaPortrait from "@/components/NovaPortrait";
import PushToTalk from "@/components/PushToTalk";
import ChatPanel from "@/components/ChatPanel";
import { Dialog, DialogContent, DialogTrigger, DialogTitle, DialogHeader } from "@/components/ui/dialog";
import { MessageSquare } from "lucide-react";

export const Layout = () => {
  const [novaState, setNovaState] = useState("idle");
  const [lastReply, setLastReply] = useState(null);

  return (
    <div className="min-h-screen bg-[color:var(--nova-bg)] text-[color:var(--nova-text)]">
      <Sidebar />

      <main className="lg:ml-64 min-h-screen">
        <div className="max-w-7xl mx-auto px-4 md:px-8 pt-16 lg:pt-10 pb-32">
          <Outlet context={{ novaState, setNovaState, lastReply, setLastReply }} />
        </div>
      </main>

      {/* Floating NOVA + Push-to-talk (mobile) */}
      <div className="lg:hidden fixed bottom-0 inset-x-0 z-40 nova-glass border-t border-[color:var(--nova-border)] px-3 py-3 flex items-center justify-between gap-2 overflow-hidden">
        <div className="flex min-w-0 items-center gap-3">
          <NovaPortrait
            state={novaState}
            variant="avatar"
            width={42}
            showLabel={false}
            testId="nova-avatar-mobile"
            priority
          />
          <div>
            <div className="font-mono-nova text-[10px] uppercase tracking-widest text-[color:var(--nova-text-3)]">NOVA</div>
            <div className="text-sm">{novaState === "idle" ? "Hazır" : novaState === "listening" ? "Dinliyor" : novaState === "thinking" ? "Düşünüyor" : "Konuşuyor"}</div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Dialog>
            <DialogTrigger asChild>
              <button aria-label="NOVA sohbetini aç" data-testid="open-chat-mobile" className="h-12 w-12 rounded-full bg-[color:var(--nova-bg-3)] grid place-items-center">
                <MessageSquare className="h-5 w-5" />
              </button>
            </DialogTrigger>
            <DialogContent data-testid="mobile-chat-dialog" className="max-w-[calc(100vw-1rem)] sm:max-w-md p-0 overflow-hidden bg-[color:var(--nova-bg-2)] border border-[color:var(--nova-border)] shadow-2xl">
              <DialogHeader className="sr-only"><DialogTitle>Sohbet</DialogTitle></DialogHeader>
              <ChatPanel onState={setNovaState} extraMessage={lastReply} />
            </DialogContent>
          </Dialog>
          <PushToTalk onState={setNovaState} onReply={setLastReply} testId="push-to-talk-button-mobile" />
        </div>
      </div>

      {/* Desktop floating NOVA panel */}
      <aside className="hidden lg:flex fixed right-4 top-4 bottom-4 w-[380px] flex-col gap-3 z-20">
        <div className="nova-glass rounded-2xl p-4 flex shrink-0 flex-col items-center gap-3">
          <NovaPortrait state={novaState} width={128} testId="nova-portrait-desktop" priority />
          <PushToTalk onState={setNovaState} onReply={setLastReply} testId="push-to-talk-button-desktop" />
          <div className="text-center text-xs text-[color:var(--nova-text-3)] font-mono-nova">
            Mikrofona dokun ve konuş
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-hidden">
          <ChatPanel onState={setNovaState} extraMessage={lastReply} />
        </div>
      </aside>

      {/* Spacer for desktop right panel */}
      <style>{`
        @media (min-width: 1024px) {
          main { padding-right: 410px; }
        }
      `}</style>
    </div>
  );
};

export default Layout;
