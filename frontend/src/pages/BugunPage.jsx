import { useEffect, useState } from "react";
import { briefingApi, tasksApi, eventsApi } from "@/lib/api";
import { toast } from "sonner";
import { Clock, Flag, Volume2, Loader2, Link2, CalendarCheck } from "lucide-react";
import { voiceApi } from "@/lib/api";
import { useOutletContext, Link } from "react-router-dom";

export default function BugunPage() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const { setNovaState } = useOutletContext();

  useEffect(() => {
    briefingApi.today()
      .then(setBriefing)
      .catch((e) => toast.error("Brifing alınamadı", { description: e?.response?.data?.detail || e.message }))
      .finally(() => setLoading(false));
  }, []);

  const speak = async () => {
    if (!briefing?.text) return;
    setPlaying(true);
    setNovaState?.("speaking");
    try {
      const blob = await voiceApi.tts(briefing.text);
      const audio = new Audio(URL.createObjectURL(blob));
      audio.onended = () => { setPlaying(false); setNovaState?.("idle"); };
      audio.play();
    } catch (e) {
      toast.error("Ses üretilemedi");
      setPlaying(false);
      setNovaState?.("idle");
    }
  };

  const now = new Date();
  const dateLabel = now.toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="space-y-6" data-testid="bugun-page">
      {/* Header */}
      <div>
        <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">Bugün</div>
        <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">
          {dateLabel.replace(/^\w/, (c) => c.toUpperCase())}
        </h1>
      </div>

      {/* Briefing */}
      <div className="nova-card p-6 md:p-7 amber-glow" data-testid="daily-briefing-card">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <div className="font-mono-nova text-xs uppercase tracking-[0.25em] text-[color:var(--nova-amber)]">Günün Brifingi</div>
            <div className="font-serif-display text-2xl mt-1">NOVA'dan size</div>
          </div>
          <button
            onClick={speak}
            disabled={playing || loading}
            data-testid="briefing-speak-button"
            className="h-10 px-4 rounded-full bg-[color:var(--nova-amber)]/15 text-[color:var(--nova-amber)] border border-[color:var(--nova-amber)]/30 flex items-center gap-2 text-sm hover:bg-[color:var(--nova-amber)]/25 transition-colors"
          >
            {playing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
            Dinle
          </button>
        </div>
        {loading ? (
          <div className="flex items-center gap-2 text-[color:var(--nova-text-2)]" data-testid="briefing-loading"><Loader2 className="h-4 w-4 animate-spin" /> Hazırlanıyor…</div>
        ) : (
          <p className="font-serif-display text-lg md:text-xl leading-relaxed text-[color:var(--nova-text)] whitespace-pre-wrap" data-testid="briefing-text">
            {briefing?.text}
          </p>
        )}
      </div>

      {/* Grid: Priorities + Timeline + Warnings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="nova-card p-5" data-testid="priorities-card">
          <div className="flex items-center gap-2 mb-3">
            <Flag className="h-4 w-4 text-[color:var(--nova-amber)]" />
            <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]">Günün 3 Önceliği</div>
          </div>
          {briefing?.priorities?.length ? (
            <ul className="space-y-2">
              {briefing.priorities.slice(0, 3).map(p => (
                <li key={p.id} className="flex items-start gap-3 text-sm">
                  <span className="nova-dot mt-2" />
                  <span className="text-[color:var(--nova-text)]">{p.title}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-[color:var(--nova-text-3)]">Henüz öncelik belirlenmedi. Bekleyen İşler'den işaretleyebilirsiniz.</div>
          )}
        </div>

        <div className="nova-card p-5" data-testid="timeline-card">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="h-4 w-4 text-[color:var(--nova-amber)]" />
            <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]">Bugünkü Takvim</div>
          </div>
          {briefing?.google_events?.length > 0 && (
            <div className="mb-3">
              <div className="font-mono-nova text-[10px] uppercase tracking-widest text-emerald-400 mb-2 flex items-center gap-1">
                <CalendarCheck className="h-3 w-3" /> Google Takvim
              </div>
              <ul className="space-y-2.5">
                {briefing.google_events.map(e => (
                  <li key={e.id} className="flex items-start gap-3 text-sm" data-testid={`google-event-${e.id}`}>
                    <span className="font-mono-nova text-xs text-[color:var(--nova-amber)] w-14 pt-0.5">
                      {e.start?.includes("T") ? e.start.slice(11, 16) : "Tüm gün"}
                    </span>
                    <div>
                      <div className="text-[color:var(--nova-text)]">{e.title}</div>
                      {e.location && <div className="text-xs text-[color:var(--nova-text-3)]">{e.location}</div>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {briefing?.events?.length > 0 && (
            <div>
              {briefing?.google_events?.length > 0 && (
                <div className="font-mono-nova text-[10px] uppercase tracking-widest text-[color:var(--nova-text-3)] mb-2">Yerel</div>
              )}
              <ul className="space-y-2.5">
                {briefing.events.map(e => (
                  <li key={e.id} className="flex items-start gap-3 text-sm">
                    <span className="font-mono-nova text-xs text-[color:var(--nova-amber)] w-14 pt-0.5">
                      {e.start_time?.slice(11, 16)}
                    </span>
                    <div>
                      <div className="text-[color:var(--nova-text)]">{e.title}</div>
                      {e.location && <div className="text-xs text-[color:var(--nova-text-3)]">{e.location}</div>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {(!briefing?.events?.length && !briefing?.google_events?.length) && (
            <div className="text-sm text-[color:var(--nova-text-3)]">
              {briefing?.google_connected
                ? "Bugün Google Takvim'de etkinlik yok."
                : "Google Takvim bağlı değil. Yerel takvimde de kayıt yok."}
            </div>
          )}
        </div>
      </div>

      {/* Google connection banner */}
      {briefing && !briefing.google_connected && (
        <div className="nova-card p-5 border-[color:var(--nova-amber)]/40" data-testid="google-connect-banner">
          <div className="flex items-start gap-3 flex-wrap">
            <Link2 className="h-5 w-5 text-[color:var(--nova-amber)] mt-0.5" />
            <div className="flex-1 min-w-0">
              <div className="font-serif-display text-lg text-[color:var(--nova-text)]">Google Takvim henüz bağlı değil</div>
              <div className="text-sm text-[color:var(--nova-text-2)] mt-1">
                Gerçek etkinlikleriniz ("NOVA ASİSTAN — Özel Takvim") brifinge dâhil edilsin diye Google hesabınızı bağlayın. NOVA yalnızca okur, değişiklik yapmaz.
              </div>
            </div>
            <Link to="/ayarlar" data-testid="banner-connect-google" className="h-10 px-4 rounded-full bg-[color:var(--nova-amber)] text-black font-medium flex items-center gap-2 text-sm">
              <Link2 className="h-4 w-4" /> Bağlan
            </Link>
          </div>
        </div>
      )}

    </div>
  );
}
