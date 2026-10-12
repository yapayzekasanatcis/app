import { useEffect, useRef, useState } from "react";
import { Send, Loader2, Paperclip, X } from "lucide-react";
import { chatApi, voiceApi, attachmentApi } from "@/lib/api";
import { toast } from "sonner";

export const ChatPanel = ({ onState, extraMessage }) => {
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const scrollRef = useRef(null);
  const audioRef = useRef(null);
  const fileRef = useRef(null);

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
    if ((!text && attachments.length === 0) || busy) return;

    const selectedFiles = attachments;

    const displayText = selectedFiles.length
      ? `${text || "Bu dosyaları incele."}\n${selectedFiles.map(f => `📎 ${f.name}`).join("\n")}`
      : text;

    setInput("");
    setAttachments([]);
    setMsgs(m => [...m, { role: "user", content: displayText, created_at: new Date().toISOString() }]);
    setBusy(true);
    onState?.("thinking");
    try {
      const result = selectedFiles.length
        ? await attachmentApi.analyze(
            selectedFiles,
            text || "Bu dosyaları birlikte incele ve önemli bilgileri çıkar."
          )
        : await chatApi.send(text);

      const { answer, sources = [] } = result;
      setMsgs(m => [...m, { role: "assistant", content: answer, sources, created_at: new Date().toISOString() }]);
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

  const visibleContent = (message) => (
    message.role === "assistant"
      ? message.content.replace(/Bora Bey/g, "Bora")
      : message.content
  );

  return (
    <div className="flex min-w-0 max-w-full flex-col h-full overflow-hidden nova-glass rounded-2xl" data-testid="chat-panel">
      <div className="p-4 border-b border-[color:var(--nova-border)]">
        <div className="font-mono-nova text-xs uppercase tracking-[0.25em] text-[color:var(--nova-text-3)]">NOVA ile sohbet</div>
        <div className="font-serif-display text-xl text-[color:var(--nova-text)] mt-1">Nasıl yardımcı olabilirim Bora?</div>
      </div>

      <div ref={scrollRef} className="flex-1 min-w-0 max-w-full overflow-x-hidden overflow-y-auto px-4 py-4 space-y-4 min-h-0">
        {msgs.length === 0 && (
          <div className="text-[color:var(--nova-text-3)] text-sm font-mono-nova">
            Örnek: "Nova bugün programımız ne?" ya da "Nova bunu not al: Cuma 16:00 merkez siparişi"
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex min-w-0 max-w-full ${m.role === "user" ? "justify-end" : "justify-start"}`} data-testid={`chat-msg-${m.role}`}>
            <div className={`min-w-0 max-w-[85%] break-words [overflow-wrap:anywhere] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap
              ${m.role === "user"
                ? "bg-[color:var(--nova-amber)] text-black"
                : "bg-[color:var(--nova-bg-3)] text-[color:var(--nova-text)] border border-[color:var(--nova-border)]"}`}>
              <div>{visibleContent(m)}</div>
              {m.role === "assistant" && m.sources?.length > 0 && (
                <div className="mt-3 border-t border-[color:var(--nova-border)] pt-2" data-testid={`chat-sources-${i}`}>
                  <div className="mb-1 text-[10px] uppercase text-[color:var(--nova-text-3)]">Kaynaklar</div>
                  {m.sources.slice(0, 5).map((source, sourceIndex) => (
                    <a
                      key={`${source.url}-${sourceIndex}`}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      data-testid={`chat-source-${i}-${sourceIndex}`}
                      className="block max-w-full break-all text-xs text-[color:var(--nova-amber-warm)] underline decoration-transparent hover:decoration-current"
                    >
                      {source.title || source.url}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-[color:var(--nova-text-2)] text-sm" data-testid="chat-thinking-status">
            <Loader2 className="h-4 w-4 animate-spin" /> NOVA düşünüyor…
          </div>
        )}
      </div>

      <div className="shrink-0 min-w-0 p-3 border-t border-[color:var(--nova-border)]">
        {attachments.length > 0 && (
          <div className="mb-2 space-y-1">
            {attachments.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center gap-2 rounded-xl border border-[color:var(--nova-border)] bg-[color:var(--nova-bg-3)] px-3 py-2 text-xs text-[color:var(--nova-text-2)]"
              >
                <Paperclip className="h-3.5 w-3.5 shrink-0" />
                <span className="min-w-0 flex-1 truncate">
                  {file.name}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    setAttachments(current =>
                      current.filter((_, i) => i !== index)
                    )
                  }
                  className="rounded-md p-1 hover:bg-white/5"
                  aria-label="Dosyayı kaldır"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp,application/pdf"
            className="hidden"
            onChange={(e) => {
              const selected = Array.from(e.target.files || []);

              if (!selected.length) return;

              const oversized = selected.find(
                file => file.size > 12 * 1024 * 1024
              );

              if (oversized) {
                toast.error(
                  "Dosya çok büyük",
                  { description: "Her dosya en fazla 12 MB olabilir." }
                );
                e.target.value = "";
                return;
              }

              setAttachments(current => {
                const combined = [...current, ...selected];

                if (combined.length > 5) {
                  toast.error(
                    "En fazla 5 dosya",
                    {
                      description:
                        "Aynı mesajda en fazla 5 dosya yükleyebilirsin."
                    }
                  );
                }

                return combined.slice(0, 5);
              });

              e.target.value = "";
            }}
          />

          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="rounded-xl border border-[color:var(--nova-border)] bg-[color:var(--nova-bg-3)] px-3 text-[color:var(--nova-text-2)] hover:text-[color:var(--nova-text)] disabled:opacity-50"
            title="Görsel veya PDF ekle"
            aria-label="Dosya ekle"
          >
            <Paperclip className="h-4 w-4" />
          </button>

        <input
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder="NOVA'ya yaz…"
          className="min-w-0 flex-1 bg-[color:var(--nova-bg-3)] text-[color:var(--nova-text)] placeholder:text-[color:var(--nova-text-3)] rounded-xl px-4 py-3 text-sm outline-none border border-transparent focus:border-[color:var(--nova-amber)]/40"
        />
        <button
          onClick={send}
          disabled={busy || (!input.trim() && attachments.length === 0)}
          data-testid="chat-send-button"
          className="rounded-xl bg-[color:var(--nova-amber)] text-black px-4 flex items-center justify-center hover:bg-[color:var(--nova-amber-hover)] transition-colors disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
        </button>
        </div>
      </div>
    </div>
  );
};

export default ChatPanel;
