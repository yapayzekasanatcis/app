import { useAuth } from "@/context/AuthContext";
import { useEffect, useState } from "react";
import { googleApi } from "@/lib/googleApi";
import { toast } from "sonner";
import { CheckCircle2, XCircle, Link2, Unlink, FileText, Table, FolderOpen, Loader2, RefreshCw } from "lucide-react";
import { useSearchParams } from "react-router-dom";

export default function AyarlarPage() {
  const { user, logout } = useAuth();
  const [status, setStatus] = useState({ configured: false, connected: false });
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verification, setVerification] = useState(null);
  const [params] = useSearchParams();

  const refresh = async () => {
    try { setStatus(await googleApi.status()); } catch {}
    setLoading(false);
  };
  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (params.get("google") === "connected") {
      toast.success("Google hesabı başarıyla bağlandı Bora Bey");
      refresh();
    }
    const err = params.get("google_error");
    if (err) toast.error(`Google bağlantı hatası: ${err}`);
  }, [params]);

  const connect = async () => {
    setConnecting(true);
    try {
      const { url } = await googleApi.connect();
      window.location.href = url;
    } catch (e) {
      toast.error("Google bağlantısı başlatılamadı", { description: e?.response?.data?.detail || e.message });
      setConnecting(false);
    }
  };

  const disconnect = async () => {
    try { await googleApi.disconnect(); setVerification(null); toast.success("Google bağlantısı kaldırıldı"); refresh(); }
    catch { toast.error("Bağlantı kaldırılamadı"); }
  };

  const verify = async () => {
    setVerifying(true);
    try {
      const result = await googleApi.verify();
      setVerification(result);
      if (result.calendar.event_found) toast.success("Google Workspace gerçek veri testi başarılı");
      else toast.warning("Takvim bağlı; aranan 8 Ekim etkinliği bulunamadı");
    } catch (e) {
      setVerification(null);
      toast.error("Workspace doğrulaması tamamlanamadı", { description: e?.response?.data?.detail || e.message });
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="ayarlar-page">
      <div>
        <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">Ayarlar</div>
        <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">Ayarlar</h1>
      </div>

      {/* Hesap */}
      <div className="nova-card p-6">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Hesap</div>
        <div className="flex items-center gap-4">
          {user?.picture && <img src={user.picture} alt="" className="h-14 w-14 rounded-full" />}
          <div>
            <div className="font-serif-display text-xl text-[color:var(--nova-text)]">{user?.name}</div>
            <div className="text-sm text-[color:var(--nova-text-3)]">{user?.email}</div>
          </div>
        </div>
      </div>

      {/* Google entegrasyonu */}
      <div className="nova-card p-6" data-testid="google-integration-card">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]">Google Entegrasyonu</div>
            <div className="font-serif-display text-2xl text-[color:var(--nova-text)] mt-1">Takvim, Sheets, Drive & Docs</div>
          </div>
          {loading ? null : status.connected ? (
            <div className="flex items-center gap-2 text-sm text-emerald-400" data-testid="google-connection-status-connected">
              <CheckCircle2 className="h-4 w-4" /> Bağlı
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-[color:var(--nova-text-3)]" data-testid="google-connection-status-disconnected">
              <XCircle className="h-4 w-4" /> Bağlı değil
            </div>
          )}
        </div>

        {!status.configured && !loading && (
          <div className="mt-4 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-sm text-red-300" data-testid="google-not-configured">
            <div className="font-medium text-red-200">Google Cloud OAuth çalışma ortamında hazır değil</div>
            {status.configuration_error && <div className="mt-1" data-testid="google-configuration-error">{status.configuration_error}</div>}
            <div className="mt-2 text-red-300/90">
              Secrets alanındaki <span className="font-mono-nova">GOOGLE_CLIENT_ID</span> ve <span className="font-mono-nova">GOOGLE_CLIENT_SECRET</span> değerlerinin çalışan ortama yansıması gerekir.
            </div>
          </div>
        )}

        {status.configured && (
          <div className="mt-4 flex items-center gap-3 flex-wrap">
            {status.connected ? (
              <>
                <button onClick={disconnect} data-testid="google-disconnect-button" className="h-11 px-5 rounded-full bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-colors text-sm flex items-center gap-2">
                  <Unlink className="h-4 w-4" /> Bağlantıyı Kaldır
                </button>
                <button onClick={verify} disabled={verifying} data-testid="google-verify-button" className="h-11 px-5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 transition-colors text-sm flex items-center gap-2 disabled:opacity-60">
                  {verifying ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Gerçek Veriyi Doğrula
                </button>
                <div className="flex items-center gap-3 text-xs text-[color:var(--nova-text-2)] font-mono-nova">
                  <span className="flex items-center gap-1"><Table className="h-3 w-3" /> NOVA İş Merkezi</span>
                  <span className="flex items-center gap-1"><FolderOpen className="h-3 w-3" /> NOVA ASİSTAN</span>
                  <span className="flex items-center gap-1"><FileText className="h-3 w-3" /> Çekirdek Kurallar</span>
                </div>
              </>
            ) : (
              <button onClick={connect} disabled={connecting} data-testid="google-connect-button" className="h-11 px-5 rounded-full bg-[color:var(--nova-amber)] text-black font-medium hover:bg-[color:var(--nova-amber-hover)] transition-colors text-sm flex items-center gap-2 disabled:opacity-60">
                {connecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />} Google'ı Bağla
              </button>
            )}
          </div>
        )}

        {verification && (
          <div className="mt-5 grid gap-3 md:grid-cols-2" data-testid="google-verification-results">
            <div className="border border-white/10 bg-white/[0.03] p-4 rounded-lg" data-testid="google-calendar-verification-result">
              <div className="font-medium text-[color:var(--nova-text)]">Özel Takvim</div>
              <div className={`mt-1 text-sm ${verification.calendar.event_found ? "text-emerald-400" : "text-amber-300"}`} data-testid="google-calendar-event-verification-status">
                {verification.calendar.event_found
                  ? "8 Ekim 2026, 20:00 konser etkinliği okundu"
                  : "8 Ekim 2026 konser etkinliği bulunamadı"}
              </div>
            </div>
            <div className="border border-white/10 bg-white/[0.03] p-4 rounded-lg" data-testid="google-sheets-verification-result">
              <div className="font-medium text-[color:var(--nova-text)]">NOVA İş Merkezi</div>
              <div className="mt-1 text-sm text-emerald-400" data-testid="google-sheets-tabs-verification-status">
                {Object.entries(verification.sheets.tabs).map(([name, tab]) => `${name}: ${tab.row_count} satır`).join(" · ")}
              </div>
            </div>
          </div>
        )}

        <div className="mt-4 text-xs text-[color:var(--nova-text-3)] space-y-1">
          <div>• Okunacak Takvim: <span className="text-[color:var(--nova-text-2)]">"NOVA ASİSTAN — Özel Takvim"</span> (yoksa birincil takvim)</div>
          <div>• Okunacak Sheet: <span className="text-[color:var(--nova-text-2)]">"NOVA İş Merkezi"</span> (sayfalar: İşler, Projeler, Rutinler)</div>
          <div>• Okunacak Klasör: <span className="text-[color:var(--nova-text-2)]">"NOVA ASİSTAN"</span></div>
          <div>• Okunacak Doküman: <span className="text-[color:var(--nova-text-2)]">"NOVA ASİSTAN — Çekirdek Kurallar ve Rutinler"</span></div>
          <div className="pt-1">İzinler: salt okuma (readonly). NOVA onayınız olmadan Google üzerinde değişiklik yapmaz.</div>
        </div>
      </div>

      {/* AI config */}
      <div className="nova-card p-6">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Yapay Zekâ</div>
        <div className="space-y-2 text-sm text-[color:var(--nova-text-2)]">
          <div>Ana Model: <span className="text-[color:var(--nova-amber)] font-mono-nova">OpenAI gpt-4o-mini</span></div>
          <div>Sesli Giriş: <span className="text-[color:var(--nova-amber)] font-mono-nova">Whisper (Türkçe)</span></div>
          <div>Sesli Çıkış: <span className="text-[color:var(--nova-amber)] font-mono-nova">gpt-4o-mini-tts</span></div>
        </div>
      </div>

      {/* Oturum */}
      <div className="nova-card p-6">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Oturum</div>
        <button onClick={logout} data-testid="settings-logout-button" className="h-11 px-5 rounded-full bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-colors text-sm">
          Çıkış Yap
        </button>
      </div>
    </div>
  );
}
