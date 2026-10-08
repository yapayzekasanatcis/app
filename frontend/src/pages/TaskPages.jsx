import { useEffect, useState } from "react";
import { tasksApi } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Check, Flag } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const CONTEXT_LABELS = {
  "kisisel": "Kişisel",
  "komagene": "Komagene",
  "tiyatral-nikah": "Tiyatral Nikâh",
  "bora-ai-studyo": "Bora AI Stüdyo",
};
const PRIORITY_LABELS = { "yuksek": "Yüksek", "normal": "Normal", "dusuk": "Düşük" };

export const TaskList = ({ context, title, subtitle, filterPriority = false }) => {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: "", description: "", priority: "normal", context: context || "kisisel", is_priority: false
  });

  const load = async () => {
    setLoading(true);
    try {
      const q = {};
      if (context) q.context = context;
      q.completed = false;
      let data = await tasksApi.list(q);
      if (filterPriority) data = data.filter(t => t.is_priority);
      setTasks(data);
    } catch (e) {
      toast.error("İşler alınamadı");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [context, filterPriority]);

  const add = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) return;
    try {
      await tasksApi.create(form);
      toast.success("İş eklendi Bora Bey");
      setForm({ title: "", description: "", priority: "normal", context: context || form.context, is_priority: filterPriority });
      setOpen(false);
      load();
    } catch (e) {
      toast.error("İş eklenemedi", { description: e?.response?.data?.detail || e.message });
    }
  };

  const toggleComplete = async (t) => {
    try {
      await tasksApi.update(t.id, { completed: true });
      toast.success("Tamamlandı");
      load();
    } catch { toast.error("Güncellenemedi"); }
  };

  const togglePriority = async (t) => {
    try {
      await tasksApi.update(t.id, { is_priority: !t.is_priority });
      load();
    } catch { toast.error("Güncellenemedi"); }
  };

  const remove = async (t) => {
    try {
      await tasksApi.remove(t.id);
      toast.success("Silindi");
      load();
    } catch { toast.error("Silinemedi"); }
  };

  return (
    <div className="space-y-6" data-testid={`task-list-${context || 'all'}`}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">{subtitle || "Liste"}</div>
          <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">{title}</h1>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <button data-testid="add-task-button" className="h-11 px-4 rounded-full bg-[color:var(--nova-amber)] text-black font-medium flex items-center gap-2 text-sm hover:bg-[color:var(--nova-amber-hover)] transition-colors">
              <Plus className="h-4 w-4" /> Yeni İş
            </button>
          </DialogTrigger>
          <DialogContent className="bg-[color:var(--nova-bg-2)] border border-[color:var(--nova-border)] text-[color:var(--nova-text)]">
            <DialogHeader><DialogTitle className="font-serif-display text-2xl">Yeni İş</DialogTitle></DialogHeader>
            <form onSubmit={add} className="space-y-3 pt-2">
              <input
                data-testid="task-title-input"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="İş başlığı"
                className="w-full bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none border border-transparent focus:border-[color:var(--nova-amber)]/40"
                required
              />
              <textarea
                data-testid="task-description-input"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Açıklama (opsiyonel)"
                rows={2}
                className="w-full bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none border border-transparent focus:border-[color:var(--nova-amber)]/40"
              />
              <div className="grid grid-cols-2 gap-3">
                <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
                  <SelectTrigger data-testid="task-priority-select" className="bg-[color:var(--nova-bg-3)] border-transparent"><SelectValue placeholder="Öncelik" /></SelectTrigger>
                  <SelectContent className="bg-[color:var(--nova-bg-2)] border-[color:var(--nova-border)] text-[color:var(--nova-text)]">
                    <SelectItem value="yuksek">Yüksek</SelectItem>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="dusuk">Düşük</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={form.context} onValueChange={(v) => setForm({ ...form, context: v })} disabled={!!context}>
                  <SelectTrigger data-testid="task-context-select" className="bg-[color:var(--nova-bg-3)] border-transparent"><SelectValue placeholder="Bağlam" /></SelectTrigger>
                  <SelectContent className="bg-[color:var(--nova-bg-2)] border-[color:var(--nova-border)] text-[color:var(--nova-text)]">
                    {Object.entries(CONTEXT_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <label className="flex items-center gap-2 text-sm text-[color:var(--nova-text-2)]">
                <input
                  type="checkbox"
                  checked={form.is_priority}
                  onChange={(e) => setForm({ ...form, is_priority: e.target.checked })}
                  className="accent-[color:var(--nova-amber)]"
                  data-testid="task-priority-checkbox"
                />
                Günün 3 önceliğinden biri
              </label>
              <button type="submit" data-testid="task-submit-button" className="w-full h-11 rounded-xl bg-[color:var(--nova-amber)] text-black font-medium hover:bg-[color:var(--nova-amber-hover)] transition-colors">
                Kaydet
              </button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="text-[color:var(--nova-text-3)]">Yükleniyor…</div>
      ) : tasks.length === 0 ? (
        <div className="nova-card p-10 text-center">
          <div className="font-serif-display text-xl text-[color:var(--nova-text-2)]">Henüz bir iş yok</div>
          <div className="text-sm text-[color:var(--nova-text-3)] mt-2">"Yeni İş" ile başlayabilirsiniz.</div>
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map(t => (
            <div key={t.id} data-testid={`task-item-${t.id}`} className="nova-card p-4 flex items-start gap-3">
              <button
                onClick={() => toggleComplete(t)}
                data-testid={`task-complete-${t.id}`}
                className="h-6 w-6 rounded-md border border-[color:var(--nova-amber)]/40 grid place-items-center hover:bg-[color:var(--nova-amber)]/10 transition-colors mt-0.5"
              >
                <Check className="h-4 w-4 text-[color:var(--nova-amber)] opacity-0 hover:opacity-100" />
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[color:var(--nova-text)]">{t.title}</span>
                  <span className={`font-mono-nova text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full
                    ${t.priority === "yuksek" ? "bg-red-500/15 text-red-400"
                      : t.priority === "dusuk" ? "bg-[color:var(--nova-bg-3)] text-[color:var(--nova-text-3)]"
                      : "bg-[color:var(--nova-amber)]/15 text-[color:var(--nova-amber)]"}`}>
                    {PRIORITY_LABELS[t.priority]}
                  </span>
                  <span className="font-mono-nova text-[10px] uppercase tracking-wider text-[color:var(--nova-text-3)]">
                    {CONTEXT_LABELS[t.context]}
                  </span>
                </div>
                {t.description && <div className="text-sm text-[color:var(--nova-text-2)] mt-1">{t.description}</div>}
              </div>
              <button
                onClick={() => togglePriority(t)}
                data-testid={`task-pin-${t.id}`}
                className={`h-9 w-9 grid place-items-center rounded-lg hover:bg-[color:var(--nova-bg-3)] transition-colors ${t.is_priority ? "text-[color:var(--nova-amber)]" : "text-[color:var(--nova-text-3)]"}`}
                aria-label="Öncelik işaretle"
              >
                <Flag className="h-4 w-4" fill={t.is_priority ? "currentColor" : "none"} />
              </button>
              <button
                onClick={() => remove(t)}
                data-testid={`task-delete-${t.id}`}
                className="h-9 w-9 grid place-items-center rounded-lg hover:bg-red-500/10 text-[color:var(--nova-text-3)] hover:text-red-400 transition-colors"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export const BekleyenIslerPage = () => <TaskList title="Bekleyen İşler" subtitle="Tüm aktif görevler" />;
export const OnceliklerPage = () => <TaskList title="Öncelikler" subtitle="Günün 3 odağı" filterPriority />;
export const KomagenePage = () => <TaskList context="komagene" title="Komagene" subtitle="İşletme operasyonu" />;
export const TiyatralNikahPage = () => <TaskList context="tiyatral-nikah" title="Tiyatral Nikâh" subtitle="Organizasyonlar & seyahatler" />;
export const BoraAIStudyoPage = () => <TaskList context="bora-ai-studyo" title="Bora AI Stüdyo" subtitle="AI projeleri & üretim" />;
export const KisiselPage = () => <TaskList context="kisisel" title="Kişisel" subtitle="Özel yaşam ve hobiler" />;
