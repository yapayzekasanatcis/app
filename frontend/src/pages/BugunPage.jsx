import { useEffect, useState } from "react";
import { briefingApi, tasksApi, eventsApi } from "@/lib/api";
import { toast } from "sonner";
import { Clock, Flag, AlertTriangle, Volume2, Loader2 } from "lucide-react";
import { voiceApi } from "@/lib/api";
import { useOutletContext } from "react-router-dom";

const WARNINGS = [
  { date: "10-11", label: "Tuğba'nın Doğum Günü", lead: 14 },
  { date: "02-14", label: "Sevgililer Günü (Tuğba)", lead: 7 },
  { date: "03-08", label: "Kadınlar Günü (Tuğba)", lead: 5 },
  { date: "05-12", label: "Bora Bey'in Doğum Günü", lead: 7 },
  { date: "07-13", label: "Anne'nin Doğum Günü", lead: 7 },
  { date: "07-29", label: "Tolga Abi'nin Doğum Günü", lead: 5 },
  { date: "01-11", label: "Atakan'ın Doğum Günü", lead: 5 },
];

function daysUntil(mmdd) {
  const now = new Date();
  const [m, d] = mmdd.split("-").map(Number);
  let target = new Date(now.getFullYear(), m - 1, d);
  if (target < new Date(now.getFullYear(), now.getMonth(), now.getDate())) {
    target = new Date(now.getFullYear() + 1, m - 1, d);
  }
  const diff = Math.ceil((target - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  return diff;
}

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

  const upcomingWarnings = WARNINGS
    .map(w => ({ ...w, days: daysUntil(w.date) }))
    .filter(w => w.days <= w.lead)
    .sort((a, b) => a.days - b.days);

  // Komagene %50 campaign reminder
  const day = now.getDate();
  if (day === 14) upcomingWarnings.unshift({ label: "Yarın %50 Bedava Çiğköfte — Balon ve afiş hazırlığı", days: 1 });
  if (day === 15) upcomingWarnings.unshift({ label: "Bugün %50 Bedava Çiğköfte Günü", days: 0 });

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
          <div className="flex items-center gap-2 text-[color:var(--nova-text-2)]"><Loader2 className="h-4 w-4 animate-spin" /> Hazırlanıyor…</div>
        ) : (
          <p className="font-serif-display text-lg md:text-xl leading-relaxed text-[color:var(--nova-text)] whitespace-pre-wrap">
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
          {briefing?.events?.length ? (
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
          ) : (
            <div className="text-sm text-[color:var(--nova-text-3)]">Bugün takvimde sabit program yok.</div>
          )}
        </div>
      </div>

      {/* Warnings */}
      {upcomingWarnings.length > 0 && (
        <div className="nova-card p-5 border-[color:var(--nova-amber)]/30" data-testid="warnings-card">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="h-4 w-4 text-[color:var(--nova-amber)]" />
            <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-amber)]">Yaklaşan Önemli Günler</div>
          </div>
          <ul className="space-y-2">
            {upcomingWarnings.map((w, i) => (
              <li key={i} className="flex items-center justify-between text-sm">
                <span className="text-[color:var(--nova-text)]">{w.label}</span>
                <span className="font-mono-nova text-xs text-[color:var(--nova-amber)]">
                  {w.days === 0 ? "BUGÜN" : w.days === 1 ? "YARIN" : `${w.days} gün`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
