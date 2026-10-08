import { useEffect, useState } from "react";
import { eventsApi, tasksApi } from "@/lib/api";
import { toast } from "sonner";

const DAYS = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"];

export default function BuHaftaPage() {
  const [eventsByDay, setEventsByDay] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const now = new Date();
    const monday = new Date(now);
    const dow = (monday.getDay() + 6) % 7;
    monday.setDate(monday.getDate() - dow);
    monday.setHours(0, 0, 0, 0);
    const sunday = new Date(monday);
    sunday.setDate(sunday.getDate() + 7);

    eventsApi.list({ start: monday.toISOString(), end: sunday.toISOString() })
      .then((ev) => {
        const map = {};
        for (let i = 0; i < 7; i++) {
          const d = new Date(monday); d.setDate(d.getDate() + i);
          map[d.toISOString().slice(0, 10)] = { date: d, items: [] };
        }
        ev.forEach(e => {
          const key = e.start_time?.slice(0, 10);
          if (map[key]) map[key].items.push(e);
        });
        setEventsByDay(map);
      })
      .catch(() => toast.error("Hafta verisi alınamadı"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6" data-testid="bu-hafta-page">
      <div>
        <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">Bu Hafta</div>
        <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">Haftalık Görünüm</h1>
      </div>

      {loading ? <div className="text-[color:var(--nova-text-3)]">Yükleniyor…</div> : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(eventsByDay).map(([key, { date, items }]) => (
            <div key={key} className="nova-card p-4" data-testid={`week-day-${key}`}>
              <div className="flex items-center justify-between mb-3">
                <div className="font-serif-display text-lg">{DAYS[date.getDay()]}</div>
                <div className="font-mono-nova text-xs text-[color:var(--nova-text-3)]">
                  {date.toLocaleDateString("tr-TR", { day: "numeric", month: "short" })}
                </div>
              </div>
              {items.length === 0 ? (
                <div className="text-xs text-[color:var(--nova-text-3)]">Boş</div>
              ) : (
                <ul className="space-y-1.5">
                  {items.map(e => (
                    <li key={e.id} className="text-sm text-[color:var(--nova-text)]">
                      <span className="font-mono-nova text-xs text-[color:var(--nova-amber)] mr-2">{e.start_time?.slice(11, 16)}</span>
                      {e.title}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
