import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuth, AuthProvider } from "@/context/AuthContext";
import { Toaster } from "sonner";
import { WorkspaceDataProvider } from "@/context/WorkspaceDataContext";

import LoginPage from "@/pages/LoginPage";
import Layout from "@/components/Layout";
import BugunPage from "@/pages/BugunPage";
import YarinPage from "@/pages/YarinPage";
import BuHaftaPage from "@/pages/BuHaftaPage";
import TakvimPage from "@/pages/TakvimPage";
import NotlarPage from "@/pages/NotlarPage";
import AyarlarPage from "@/pages/AyarlarPage";
import {
  BekleyenIslerPage, OnceliklerPage, KomagenePage,
  TiyatralNikahPage, BoraAIStudyoPage, KisiselPage
} from "@/pages/TaskPages";

const Protected = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="min-h-screen grid place-items-center text-[color:var(--nova-text-3)]">
      <div className="font-mono-nova text-xs uppercase tracking-widest">NOVA hazırlanıyor…</div>
    </div>
  );
  if (!user) return <Navigate to="/giris" replace />;
  return children;
};

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster
          theme="dark"
          position="top-right"
          toastOptions={{
            style: {
              background: "#161412",
              color: "#F4F1EA",
              border: "1px solid rgba(245, 158, 11, 0.2)",
            }
          }}
        />
        <Routes>
          <Route path="/giris" element={<LoginPage />} />
          <Route path="/" element={<Protected><WorkspaceDataProvider><Layout /></WorkspaceDataProvider></Protected>}>
            <Route index element={<BugunPage />} />
            <Route path="yarin" element={<YarinPage />} />
            <Route path="bu-hafta" element={<BuHaftaPage />} />
            <Route path="bekleyen-isler" element={<BekleyenIslerPage />} />
            <Route path="oncelikler" element={<OnceliklerPage />} />
            <Route path="takvim" element={<TakvimPage />} />
            <Route path="komagene" element={<KomagenePage />} />
            <Route path="tiyatral-nikah" element={<TiyatralNikahPage />} />
            <Route path="bora-ai-studyo" element={<BoraAIStudyoPage />} />
            <Route path="kisisel" element={<KisiselPage />} />
            <Route path="notlar" element={<NotlarPage />} />
            <Route path="ayarlar" element={<AyarlarPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
