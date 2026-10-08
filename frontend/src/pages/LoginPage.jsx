import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { NovaPortrait } from "@/components/NovaPortrait";

export default function LoginPage() {
  const { user, loading, refresh, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const once = useRef(false);
  const [authError, setAuthError] = useState("");
  const isOAuthCallback = location.hash.includes("session_id=");

  useEffect(() => {
    // Handle fragment from Emergent Auth callback: #session_id=XXX
    if (once.current) return;
    const hash = location.hash;
    if (hash.includes("session_id=")) {
      once.current = true;
      setUser(null);
      const sid = new URLSearchParams(hash.slice(1)).get("session_id");
      if (sid) {
        authApi.session(sid)
          .then(async () => {
            await refresh();
            toast.success("Hoş geldin Bora");
            navigate("/", { replace: true });
          })
          .catch((error) => {
            const message = error?.response?.data?.detail || "Giriş başarısız";
            setAuthError(message);
            toast.error(message);
            navigate("/giris", { replace: true });
          });
      }
    }
  }, [location.hash, navigate, refresh, setUser]);

  useEffect(() => {
    if (!isOAuthCallback && !loading && user) navigate("/", { replace: true });
  }, [isOAuthCallback, loading, user, navigate]);

  const login = () => {
    setAuthError("");
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirect = `${window.location.origin}/giris`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirect)}`;
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-10 nova-grain">
      <div className="w-full max-w-md flex flex-col items-center gap-7 md:gap-8">
        <div className="flex flex-col items-center gap-3" data-testid="login-nova-identity">
          <NovaPortrait
            state="idle"
            width="clamp(190px, 25vw, 230px)"
            showLabel={false}
            testId="nova-portrait-login"
            priority
          />
          <div className="inline-flex items-center gap-2 font-mono-nova text-[10px] uppercase tracking-[0.24em] text-[color:var(--nova-text-2)]" data-testid="login-nova-status">
            <span className="nova-dot" /> Hazır
          </div>
        </div>

        <div className="text-center">
          <div className="font-mono-nova text-xs uppercase tracking-[0.4em] text-[color:var(--nova-text-3)]">Hoş geldiniz</div>
          <h1 className="font-serif-display text-4xl sm:text-5xl mt-3 text-[color:var(--nova-text)]">NOVA ASİSTAN</h1>
          <p className="text-sm text-[color:var(--nova-text-2)] mt-3 max-w-sm">
            Bora'nın kişisel özel sekreteri. Takvim, iş, seyahat ve günlük yaşam tek merkezden koordine edilir.
          </p>
        </div>

        {authError && (
          <div
            role="alert"
            aria-live="assertive"
            data-testid="login-access-denied-alert"
            className="w-full border border-red-400/35 bg-red-950/35 px-4 py-3 text-center text-sm leading-relaxed text-red-100"
          >
            {authError}
          </div>
        )}

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
