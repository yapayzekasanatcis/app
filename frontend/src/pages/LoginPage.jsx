import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { NovaOrb } from "@/components/NovaOrb";

export default function LoginPage() {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const once = useRef(false);

  useEffect(() => {
    // Handle fragment from Emergent Auth callback: #session_id=XXX
    if (once.current) return;
    const hash = window.location.hash;
    if (hash.includes("session_id=")) {
      once.current = true;
      const sid = new URLSearchParams(hash.slice(1)).get("session_id");
      if (sid) {
        authApi.session(sid)
          .then(() => { toast.success("Hoş geldiniz Bora Bey"); refresh(); navigate("/", { replace: true }); })
          .catch(() => toast.error("Giriş başarısız"));
      }
    }
  }, [navigate, refresh]);

  useEffect(() => {
    if (!loading && user) navigate("/", { replace: true });
  }, [loading, user, navigate]);

  const login = () => {
    const redirect = `${window.location.origin}/giris`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirect)}`;
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-10 nova-grain">
      <div className="w-full max-w-md flex flex-col items-center gap-10">
        <NovaOrb state="idle" size={180} />

        <div className="text-center">
          <div className="font-mono-nova text-xs uppercase tracking-[0.4em] text-[color:var(--nova-text-3)]">Hoş geldiniz</div>
          <h1 className="font-serif-display text-5xl mt-3 text-[color:var(--nova-text)]">NOVA ASİSTAN</h1>
          <p className="text-sm text-[color:var(--nova-text-2)] mt-3 max-w-sm">
            Bora Bey'in kişisel özel sekreteri. Takvim, iş, seyahat ve günlük yaşam tek merkezden koordine edilir.
          </p>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-[color:var(--nova-text-2)]"><Loader2 className="h-4 w-4 animate-spin" /> Hazırlanıyor…</div>
        ) : (
          <button
            onClick={login}
            data-testid="google-login-button"
            className="w-full h-12 rounded-full bg-[color:var(--nova-amber)] text-black font-medium hover:bg-[color:var(--nova-amber-hover)] transition-colors flex items-center justify-center gap-2"
          >
            <svg width="18" height="18" viewBox="0 0 48 48"><path fill="#000" d="M44.5 20H24v8.5h11.8C34.7 33.4 30 36.5 24 36.5c-6.9 0-12.5-5.6-12.5-12.5S17.1 11.5 24 11.5c3.2 0 6.1 1.2 8.3 3.1l6-6C34.6 5 29.6 3 24 3 12.3 3 3 12.3 3 24s9.3 21 21 21 21-9.3 21-21c0-1.4-.2-2.7-.5-4z"/></svg>
            Google ile giriş yap
          </button>
        )}

        <div className="font-mono-nova text-[10px] uppercase tracking-widest text-[color:var(--nova-text-3)]">
          novaasistan.com
        </div>
      </div>
    </div>
  );
}
