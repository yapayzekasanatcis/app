import { useEffect, useState } from "react";
import { eventsApi, tasksApi } from "@/lib/api";
import { toast } from "sonner";

function dayStart(offsetDays = 0) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + offsetDays);
  return d;
}

export default function YarinPage() {
  const [events, setEvents] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const start = dayStart(1);
    const end = dayStart(2);
    Promise.all([
      eventsApi.list({ start: start.toISOString(), end: end.toISOString() }),
      tasksApi.list({ completed: false }),
    ])
      .then(([ev, ts]) => { setEvents(ev); setTasks(ts); })
      .catch(() => toast.error("Yarının verileri alınamadı"))
      .finally(() => setLoading(false));
  }, []);

  const now = new Date();
  const tomorrowStr = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    .toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="space-y-6" data-testid="yarin-page">
      <div>
        <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">Yarın</div>
        <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">{tomorrowStr}</h1>
      </div>

      <div className="nova-card p-5">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Yarının Programı</div>
        {loading ? <div className="text-[color:var(--nova-text-3)]">Yükleniyor…</div>
          : events.length === 0 ? <div className="text-sm text-[color:var(--nova-text-3)]">Yarın için takvimde sabit program yok.</div>
          : <ul className="space-y-2">
              {events.map(e => (
                <li key={e.id} className="flex items-start gap-3 text-sm">
                  <span className="font-mono-nova text-xs text-[color:var(--nova-amber)] w-14 pt-0.5">{e.start_time?.slice(11,16)}</span>
                  <div>
                    <div className="text-[color:var(--nova-text)]">{e.title}</div>
                    {e.location && <div className="text-xs text-[color:var(--nova-text-3)]">{e.location}</div>}
                  </div>
                </li>
              ))}
            </ul>}
      </div>

      <div className="nova-card p-5">
        <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)] mb-3">Hazırlık / Ön Kontroller</div>
        {tasks.filter(t => t.is_priority).length === 0 ? (
          <div className="text-sm text-[color:var(--nova-text-3)]">Hazırlık gerektiren işaretli iş yok.</div>
        ) : (
          <ul className="space-y-2">
            {tasks.filter(t => t.is_priority).slice(0, 5).map(t => (
              <li key={t.id} className="flex items-start gap-3 text-sm">
                <span className="nova-dot mt-2" />
                <span className="text-[color:var(--nova-text)]">{t.title}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
