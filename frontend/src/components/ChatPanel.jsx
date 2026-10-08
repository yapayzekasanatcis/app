import { useEffect, useRef, useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { chatApi, voiceApi } from "@/lib/api";
import { toast } from "sonner";

export const ChatPanel = ({ onState, extraMessage }) => {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => {
    chatApi.history().then((rows) => setMsgs(rows)).catch(() => {});
  }, []);

  useEffect(() => {
    if (extraMessage) {
      setMsgs(m => [...m,
        { role: "user", content: extraMessage.question, created_at: new Date().toISOString() },
        { role: "assistant", content: extraMessage.answer, created_at: new Date().toISOString() },
      ]);
    }
  }, [extraMessage]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [msgs]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMsgs(m => [...m, { role: "user", content: text, created_at: new Date().toISOString() }]);
    setBusy(true);
    onState?.("thinking");
    try {
      const { answer } = await chatApi.send(text);
      setMsgs(m => [...m, { role: "assistant", content: answer, created_at: new Date().toISOString() }]);
      onState?.("speaking");
      try {
        const audioBlob = await voiceApi.tts(answer);
        const url = URL.createObjectURL(audioBlob);
        if (audioRef.current) audioRef.current.pause();
        audioRef.current = new Audio(url);
        audioRef.current.onended = () => onState?.("idle");
        audioRef.current.play();
      } catch {
        onState?.("idle");
      }
    } catch (e) {
      toast.error("NOVA yanıt veremedi", { description: e?.response?.data?.detail || e.message });
      onState?.("idle");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col h-full nova-glass rounded-2xl" data-testid="chat-panel">
      <div className="p-4 border-b border-[color:var(--nova-border)]">
        <div className="font-mono-nova text-xs uppercase tracking-[0.25em] text-[color:var(--nova-text-3)]">NOVA ile sohbet</div>
        <div className="font-serif-display text-xl text-[color:var(--nova-text)] mt-1">Nasıl yardımcı olabilirim Bora Bey?</div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5 space-y-4 min-h-[280px] max-h-[55vh]">
        {msgs.length === 0 && (
          <div className="text-[color:var(--nova-text-3)] text-sm font-mono-nova">
            Örnek: "Nova bugün programımız ne?" ya da "Nova bunu not al: Cuma 16:00 merkez siparişi"
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`} data-testid={`chat-msg-${m.role}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap
              ${m.role === "user"
                ? "bg-[color:var(--nova-amber)] text-black"
                : "bg-[color:var(--nova-bg-3)] text-[color:var(--nova-text)] border border-[color:var(--nova-border)]"}`}>
              {m.content}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-[color:var(--nova-text-2)] text-sm">
            <Loader2 className="h-4 w-4 animate-spin" /> NOVA düşünüyor…
          </div>
        )}
      </div>

      <div className="p-3 border-t border-[color:var(--nova-border)] flex gap-2">
        <input
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder="NOVA'ya yaz…"
          className="flex-1 bg-[color:var(--nova-bg-3)] text-[color:var(--nova-text)] placeholder:text-[color:var(--nova-text-3)] rounded-xl px-4 py-3 text-sm outline-none border border-transparent focus:border-[color:var(--nova-amber)]/40"
        />
        <button
          onClick={send}
          disabled={busy || !input.trim()}
          data-testid="chat-send-button"
          className="rounded-xl bg-[color:var(--nova-amber)] text-black px-4 flex items-center justify-center hover:bg-[color:var(--nova-amber-hover)] transition-colors disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

export default ChatPanel;
