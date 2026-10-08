import { useEffect, useState } from "react";
import { briefingApi } from "@/lib/api";
import { toast } from "sonner";
import { Clock, Flag, Volume2, Loader2, Link2, CalendarCheck } from "lucide-react";
import { voiceApi } from "@/lib/api";
import { useOutletContext, Link } from "react-router-dom";
import { useWorkspaceData } from "@/context/WorkspaceDataContext";
import { NovaPortrait } from "@/components/NovaPortrait";

export default function BugunPage() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const { novaState, setNovaState } = useOutletContext();
  const { data: workspace } = useWorkspaceData();
  const todayEvents = workspace?.today_events || [];
  const priorities = workspace?.priorities || [];

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
      <div className="nova-card p-4 sm:p-6 md:p-7 amber-glow" data-testid="daily-briefing-card">
        <div className="grid grid-cols-[82px_minmax(0,1fr)] sm:grid-cols-[110px_minmax(0,1fr)] md:grid-cols-[132px_minmax(0,1fr)] gap-4 sm:gap-6 items-start">
          <div className="flex flex-col items-center gap-2" data-testid="dashboard-nova-identity">
            <NovaPortrait
              state={novaState}
              width="clamp(82px, 12vw, 132px)"
              showLabel={false}
              testId="nova-portrait-dashboard"
              priority
            />
            <div className="inline-flex items-center gap-1.5 font-mono-nova text-[9px] uppercase tracking-wider text-[color:var(--nova-text-3)]" data-testid="dashboard-nova-status">
              <span className="nova-dot" /> {novaState === "listening" ? "Dinliyor" : novaState === "thinking" ? "Düşünüyor" : novaState === "speaking" ? "Konuşuyor" : "Hazır"}
            </div>
          </div>
          <div className="min-w-0">
            <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
              <div>
                <div className="font-mono-nova text-[10px] sm:text-xs uppercase tracking-[0.22em] text-[color:var(--nova-amber)]">Günün Brifingi</div>
                <div className="font-serif-display text-xl sm:text-2xl mt-1">NOVA'dan sana</div>
              </div>
              <button
                onClick={speak}
                disabled={playing || loading}
                data-testid="briefing-speak-button"
                className="h-9 sm:h-10 px-3 sm:px-4 rounded-full bg-[color:var(--nova-amber)]/15 text-[color:var(--nova-amber)] border border-[color:var(--nova-amber)]/30 flex items-center gap-2 text-xs sm:text-sm hover:bg-[color:var(--nova-amber)]/25 transition-colors"
              >
                {playing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
                Dinle
              </button>
            </div>
            {loading ? (
              <div className="flex items-center gap-2 text-[color:var(--nova-text-2)]" data-testid="briefing-loading"><Loader2 className="h-4 w-4 animate-spin" /> Hazırlanıyor…</div>
            ) : (
              <p className="font-serif-display text-base sm:text-lg md:text-xl leading-relaxed text-[color:var(--nova-text)] whitespace-pre-wrap" data-testid="briefing-text">
                {briefing?.text}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Grid: Priorities + Timeline + Warnings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="nova-card p-5" data-testid="priorities-card">
          <div className="flex items-center gap-2 mb-3">
            <Flag className="h-4 w-4 text-[color:var(--nova-amber)]" />
            <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]">Günün 3 Önceliği</div>
          </div>
          {priorities.length ? (
            <ul className="space-y-2">
              {priorities.slice(0, 3).map(p => (
                <li key={p.id} className="flex items-start gap-3 text-sm" data-testid={`today-priority-${p.id}`}>
                  <span className="nova-dot mt-2" />
                  <span className="text-[color:var(--nova-text)]">{p.title}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-[color:var(--nova-text-3)]">NOVA İş Merkezi'nde öncelik üretilecek aktif kayıt yok.</div>
          )}
        </div>

        <div className="nova-card p-5" data-testid="timeline-card">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="h-4 w-4 text-[color:var(--nova-amber)]" />
            <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]">Bugünkü Takvim</div>
          </div>
          {todayEvents.length > 0 && (
            <div className="mb-3">
              <div className="font-mono-nova text-[10px] uppercase tracking-widest text-emerald-400 mb-2 flex items-center gap-1">
                <CalendarCheck className="h-3 w-3" /> Google Takvim
              </div>
              <ul className="space-y-2.5">
                {todayEvents.map(e => (
                  <li key={e.id} className="flex items-start gap-3 text-sm" data-testid={`google-event-${e.id}`}>
                    <span className="font-mono-nova text-xs text-[color:var(--nova-amber)] w-14 pt-0.5">
                      {e.start_time?.includes("T") ? e.start_time.slice(11, 16) : "Tüm gün"}
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
          {!todayEvents.length && (
            <div className="text-sm text-[color:var(--nova-text-3)]">
              {workspace?.sources?.calendar?.connected
                ? "Bugün Google Takvim'de etkinlik yok."
                : "Google Takvim verisi şu anda alınamıyor."}
            </div>
          )}
        </div>
      </div>

      {/* Google connection banner */}
      {workspace && !workspace.sources?.calendar?.connected && (
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
