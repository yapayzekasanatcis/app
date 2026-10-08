import { useAuth } from "@/context/AuthContext";

export default function AyarlarPage() {
  const { user, logout } = useAuth();
  return (
    <div className="space-y-6" data-testid="ayarlar-page">
      <div>
        <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">Ayarlar</div>
        <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">Ayarlar</h1>
      </div>

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

      <div className="nova-card p-6">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Yapay Zekâ</div>
        <div className="space-y-2 text-sm text-[color:var(--nova-text-2)]">
          <div>Ana Model: <span className="text-[color:var(--nova-amber)] font-mono-nova">OpenAI gpt-4o-mini</span> (ekonomik)</div>
          <div>Sesli Giriş: <span className="text-[color:var(--nova-amber)] font-mono-nova">Whisper (Türkçe)</span></div>
          <div>Sesli Çıkış: <span className="text-[color:var(--nova-amber)] font-mono-nova">OpenAI gpt-4o-mini-tts</span></div>
          <div className="pt-2 text-xs text-[color:var(--nova-text-3)]">Universal Key kullanılıyor. Kendi OpenAI anahtarınızı ileride ekleyebilirsiniz.</div>
        </div>
      </div>

      <div className="nova-card p-6">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Google Entegrasyonu</div>
        <div className="text-sm text-[color:var(--nova-text-2)]">
          Giriş yapan hesap: <span className="text-[color:var(--nova-text)]">{user?.email}</span>
        </div>
        <div className="mt-3 text-xs text-[color:var(--nova-text-3)]">
          Google Calendar, Drive, Sheets ve Gmail bağlantıları sonraki fazda eklenecektir. Şu anda yerel veri kullanılıyor.
        </div>
      </div>

      <div className="nova-card p-6">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Oturum</div>
        <button
          onClick={logout}
          data-testid="settings-logout-button"
          className="h-11 px-5 rounded-full bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25 transition-colors text-sm"
        >
          Çıkış Yap
        </button>
      </div>
    </div>
  );
}
