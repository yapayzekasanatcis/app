import { NavLink, useNavigate } from "react-router-dom";
import {
  Sun, Sunrise, CalendarDays, ListTodo, Flag, Calendar as CalIcon,
  Store, Heart, Sparkles, User, StickyNote, Settings, LogOut, Menu, X
} from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

const NAV = [
  { to: "/", label: "Bugün", icon: Sun, testId: "nav-bugun" },
  { to: "/yarin", label: "Yarın", icon: Sunrise, testId: "nav-yarin" },
  { to: "/bu-hafta", label: "Bu Hafta", icon: CalendarDays, testId: "nav-bu-hafta" },
  { to: "/bekleyen-isler", label: "Bekleyen İşler", icon: ListTodo, testId: "nav-bekleyen" },
  { to: "/oncelikler", label: "Öncelikler", icon: Flag, testId: "nav-oncelikler" },
  { to: "/takvim", label: "Takvim", icon: CalIcon, testId: "nav-takvim" },
  { divider: "İş & Bağlam" },
  { to: "/komagene", label: "Komagene", icon: Store, testId: "nav-komagene" },
  { to: "/tiyatral-nikah", label: "Tiyatral Nikâh", icon: Heart, testId: "nav-tiyatral" },
  { to: "/bora-ai-studyo", label: "Bora AI Stüdyo", icon: Sparkles, testId: "nav-bora-ai" },
  { to: "/kisisel", label: "Kişisel", icon: User, testId: "nav-kisisel" },
  { divider: "Diğer" },
  { to: "/notlar", label: "Notlar", icon: StickyNote, testId: "nav-notlar" },
  { to: "/ayarlar", label: "Ayarlar", icon: Settings, testId: "nav-ayarlar" },
];

export const Sidebar = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = async () => {
    await logout();
    navigate("/giris");
  };

  const content = (
    <>
      <div className="px-5 pt-6 pb-5 border-b border-[color:var(--nova-border)]">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-[color:var(--nova-amber)] grid place-items-center text-black font-serif-display text-xl font-semibold">N</div>
          <div className="min-w-0">
            <div className="font-serif-display text-xl text-[color:var(--nova-text)] leading-tight">
              NOVA
            </div>
            <div className="font-mono-nova text-[10px] uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">
              ASİSTAN SİSTEMİ
            </div>
            <div className="mt-1 font-mono-nova text-[8px] uppercase tracking-[0.22em] text-[color:var(--nova-amber)]/70">
              BORA AI STÜDYO
            </div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {NAV.map((item, i) =>
          item.divider ? (
            <div key={i} className="pt-5 pb-2 px-2 font-mono-nova text-[10px] uppercase tracking-[0.25em] text-[color:var(--nova-text-3)]">
              {item.divider}
            </div>
          ) : (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              data-testid={item.testId}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors text-sm
                 ${isActive
                   ? "bg-[color:var(--nova-amber)]/15 text-[color:var(--nova-amber)] border border-[color:var(--nova-amber)]/25"
                   : "text-[color:var(--nova-text-2)] hover:bg-[color:var(--nova-bg-3)] hover:text-[color:var(--nova-text)] border border-transparent"}`
              }
            >
              <item.icon className="h-4 w-4" />
              <span>{item.label}</span>
            </NavLink>
          )
        )}
      </nav>

      {user && (
        <div className="p-3 border-t border-[color:var(--nova-border)]">
          <div className="flex items-center gap-3 px-2 py-2">
            <Avatar className="h-9 w-9">
              <AvatarImage src={user.picture} alt={user.name} />
              <AvatarFallback className="bg-[color:var(--nova-bg-3)] text-[color:var(--nova-amber)]">
                {user.name?.[0] || "B"}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <div className="text-sm text-[color:var(--nova-text)] truncate">{user.name}</div>
              <div className="text-[11px] text-[color:var(--nova-text-3)] truncate">{user.email}</div>
            </div>
            <button
              onClick={handleLogout}
              data-testid="logout-button"
              className="text-[color:var(--nova-text-3)] hover:text-[color:var(--nova-amber)] transition-colors p-1"
              aria-label="Çıkış"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={() => setOpen(true)}
        data-testid="mobile-menu-button"
        className="lg:hidden fixed top-4 left-4 z-50 h-10 w-10 rounded-xl nova-glass grid place-items-center text-[color:var(--nova-text)]"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed left-0 top-0 bottom-0 w-64 flex-col nova-glass border-r border-[color:var(--nova-border)] z-30">
        {content}
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-50 flex" onClick={() => setOpen(false)}>
          <aside className="w-72 h-full flex flex-col bg-[color:var(--nova-bg)] border-r border-[color:var(--nova-border)]" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-end p-3">
              <button onClick={() => setOpen(false)} className="h-9 w-9 rounded-lg hover:bg-[color:var(--nova-bg-3)] grid place-items-center">
                <X className="h-5 w-5" />
              </button>
            </div>
            {content}
          </aside>
          <div className="flex-1 bg-black/60 backdrop-blur-sm" />
        </div>
      )}
    </>
  );
};

export default Sidebar;
