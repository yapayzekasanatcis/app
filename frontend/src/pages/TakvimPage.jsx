import { useEffect, useState } from "react";
import { eventsApi } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Calendar as CalIcon, MapPin } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Calendar } from "@/components/ui/calendar";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { tr } from "date-fns/locale";

const CONTEXT_LABELS = {
  "kisisel": "Kişisel",
  "komagene": "Komagene",
  "tiyatral-nikah": "Tiyatral Nikâh",
  "bora-ai-studyo": "Bora AI Stüdyo",
};

export default function TakvimPage() {
  const [events, setEvents] = useState([]);
  const [selected, setSelected] = useState(new Date());
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    title: "", description: "", start_time: "", end_time: "", location: "", context: "kisisel"
  });

  const load = async () => {
    try {
      const data = await eventsApi.list();
      setEvents(data);
    } catch { toast.error("Etkinlikler alınamadı"); }
  };
  useEffect(() => { load(); }, []);

  const add = async (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.start_time) return toast.error("Başlık ve başlangıç saati gerekli");
    try {
      await eventsApi.create(form);
      toast.success("Etkinlik eklendi");
      setForm({ title: "", description: "", start_time: "", end_time: "", location: "", context: "kisisel" });
      setOpen(false);
      load();
    } catch (e) { toast.error("Eklenemedi", { description: e?.response?.data?.detail || e.message }); }
  };

  const remove = async (id) => {
    try { await eventsApi.remove(id); toast.success("Silindi"); load(); } catch { toast.error("Silinemedi"); }
  };

  const selectedKey = selected ? selected.toISOString().slice(0, 10) : null;
  const dayEvents = selectedKey ? events.filter(e => e.start_time?.slice(0, 10) === selectedKey) : [];
  const markedDates = Array.from(new Set(events.map(e => e.start_time?.slice(0, 10)))).map(k => new Date(k));

  return (
    <div className="space-y-6" data-testid="takvim-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">Takvim</div>
          <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">Zaman Çizgisi</h1>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <button data-testid="add-event-button" className="h-11 px-4 rounded-full bg-[color:var(--nova-amber)] text-black font-medium flex items-center gap-2 text-sm hover:bg-[color:var(--nova-amber-hover)] transition-colors">
              <Plus className="h-4 w-4" /> Yeni Etkinlik
            </button>
          </DialogTrigger>
          <DialogContent className="bg-[color:var(--nova-bg-2)] border border-[color:var(--nova-border)] text-[color:var(--nova-text)]">
            <DialogHeader><DialogTitle className="font-serif-display text-2xl">Yeni Etkinlik</DialogTitle></DialogHeader>
            <form onSubmit={add} className="space-y-3 pt-2">
              <input
                data-testid="event-title-input"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                placeholder="Başlık"
                className="w-full bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none"
                required
              />
              <div className="grid grid-cols-2 gap-3">
                <input
                  data-testid="event-start-input"
                  type="datetime-local"
                  value={form.start_time}
                  onChange={(e) => setForm({ ...form, start_time: e.target.value })}
                  className="bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none"
                  required
                />
                <input
                  data-testid="event-end-input"
                  type="datetime-local"
                  value={form.end_time}
                  onChange={(e) => setForm({ ...form, end_time: e.target.value })}
                  className="bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none"
                />
              </div>
              <input
                data-testid="event-location-input"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="Konum"
                className="w-full bg-[color:var(--nova-bg-3)] rounded-xl px-4 py-3 text-sm outline-none"
              />
              <Select value={form.context} onValueChange={(v) => setForm({ ...form, context: v })}>
                <SelectTrigger data-testid="event-context-select" className="bg-[color:var(--nova-bg-3)] border-transparent"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[color:var(--nova-bg-2)] border-[color:var(--nova-border)] text-[color:var(--nova-text)]">
                  {Object.entries(CONTEXT_LABELS).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                </SelectContent>
              </Select>
              <button type="submit" data-testid="event-submit-button" className="w-full h-11 rounded-xl bg-[color:var(--nova-amber)] text-black font-medium">Kaydet</button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="nova-card p-4 lg:col-span-2">
          <Calendar
            mode="single"
            locale={tr}
            selected={selected}
            onSelect={setSelected}
            modifiers={{ marked: markedDates }}
            modifiersClassNames={{ marked: "bg-[color:var(--nova-amber)]/20 text-[color:var(--nova-amber)] rounded-md" }}
            className="w-full"
            data-testid="calendar-widget"
          />
        </div>
        <div className="nova-card p-5 lg:col-span-3">
          <div className="flex items-center gap-2 mb-4">
            <CalIcon className="h-4 w-4 text-[color:var(--nova-amber)]" />
            <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]">
              {selected?.toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
            </div>
          </div>
          {dayEvents.length === 0 ? (
            <div className="text-sm text-[color:var(--nova-text-3)]">Bu gün için etkinlik yok.</div>
          ) : (
            <ul className="space-y-3">
              {dayEvents.map(e => (
                <li key={e.id} className="flex items-start gap-3 p-3 rounded-xl bg-[color:var(--nova-bg-3)]" data-testid={`event-item-${e.id}`}>
                  <span className="font-mono-nova text-sm text-[color:var(--nova-amber)] pt-0.5">{e.start_time?.slice(11, 16)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-[color:var(--nova-text)]">{e.title}</div>
                    {e.location && <div className="text-xs text-[color:var(--nova-text-3)] flex items-center gap-1 mt-0.5"><MapPin className="h-3 w-3" /> {e.location}</div>}
                  </div>
                  <button onClick={() => remove(e.id)} className="text-[color:var(--nova-text-3)] hover:text-red-400 transition-colors"><Trash2 className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
