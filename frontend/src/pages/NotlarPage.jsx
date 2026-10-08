import { useEffect, useState } from "react";
import { notesApi } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";

export default function NotlarPage() {
  const [notes, setNotes] = useState([]);
  const [form, setForm] = useState({ title: "", content: "", category: "genel", context: "kisisel" });
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try { setNotes(await notesApi.list()); } catch { toast.error("Notlar alınamadı"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const add = async (e) => {
    e.preventDefault();
    if (!form.content.trim()) return;
    try {
      await notesApi.create(form);
      toast.success("Not kaydedildi Bora");
      setForm({ title: "", content: "", category: "genel", context: "kisisel" });
      load();
    } catch { toast.error("Kaydedilemedi"); }
  };

  const remove = async (id) => {
    try { await notesApi.remove(id); toast.success("Silindi"); load(); } catch { toast.error("Silinemedi"); }
  };

  return (
    <div className="space-y-6" data-testid="notlar-page">
      <div>
        <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">Notlar</div>
        <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">Hızlı Notlar</h1>
      </div>

      <form onSubmit={add} className="nova-card p-5 space-y-3" data-testid="note-form">
        <input
          data-testid="note-title-input"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          placeholder="Not başlığı (opsiyonel)"
          className="w-full bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none"
        />
        <textarea
          data-testid="note-content-input"
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
          placeholder="Not içeriği…"
          rows={3}
          className="w-full bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none"
          required
        />
        <div className="flex justify-end">
          <button type="submit" data-testid="note-submit-button" className="h-11 px-5 rounded-full bg-[color:var(--nova-amber)] text-black font-medium flex items-center gap-2 text-sm hover:bg-[color:var(--nova-amber-hover)] transition-colors">
            <Plus className="h-4 w-4" /> Kaydet
          </button>
        </div>
      </form>

      {loading ? <div className="text-[color:var(--nova-text-3)]">Yükleniyor…</div> :
        notes.length === 0 ? (
          <div className="nova-card p-10 text-center">
            <div className="font-serif-display text-xl text-[color:var(--nova-text-2)]">Henüz not yok</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {notes.map(n => (
              <div key={n.id} className="nova-card p-4" data-testid={`note-item-${n.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    {n.title && <div className="font-serif-display text-lg text-[color:var(--nova-text)]">{n.title}</div>}
                    <div className="text-sm text-[color:var(--nova-text-2)] mt-1 whitespace-pre-wrap">{n.content}</div>
                    <div className="font-mono-nova text-[10px] uppercase tracking-widest text-[color:var(--nova-text-3)] mt-2">
                      {new Date(n.created_at).toLocaleString("tr-TR")}
                    </div>
                  </div>
                  <button onClick={() => remove(n.id)} className="text-[color:var(--nova-text-3)] hover:text-red-400 transition-colors"><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
            ))}
          </div>
        )
      }
    </div>
  );
}
