import { useEffect, useState } from "react";
import { Calendar as CalIcon } from "lucide-react";
import { Calendar } from "@/components/ui/calendar";
import { tr } from "date-fns/locale";
import { useWorkspaceData } from "@/context/WorkspaceDataContext";
import { EventItem, PageHeader, WorkspaceState } from "@/components/WorkspaceViews";

const dateKey = (value) => value
  ? `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`
  : null;

export default function TakvimPage() {
  const { data, loading, error, refresh } = useWorkspaceData();
  const [selected, setSelected] = useState(new Date());
  const events = data?.calendar_events || [];

  useEffect(() => {
    if (data?.anchor_date) setSelected(new Date(`${data.anchor_date}T12:00:00`));
  }, [data?.anchor_date]);

  const selectedKey = dateKey(selected);
  const dayEvents = events.filter(event => event.start_time?.slice(0, 10) === selectedKey);
  const markedDates = Array.from(new Set(events.map(event => event.start_time?.slice(0, 10))))
    .filter(Boolean).map(key => new Date(`${key}T12:00:00`));

  return (
    <div className="space-y-8" data-testid="takvim-page">
      <PageHeader eyebrow="Takvim" title="Zaman Çizgisi" source="Google Calendar · NOVA Özel Takvim" />
      <WorkspaceState loading={loading} error={error} empty={false} onRetry={refresh} testId="calendar-view">
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
          <section className="nova-card p-5 lg:col-span-3" data-testid="calendar-day-events">
            <div className="flex items-center gap-2 mb-4">
              <CalIcon className="h-4 w-4 text-[color:var(--nova-amber)]" />
              <div className="font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]" data-testid="selected-calendar-date">
                {selected?.toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
              </div>
            </div>
            {dayEvents.length ? (
              <div className="space-y-3">{dayEvents.map(event => <EventItem key={event.id} event={event} testId={`calendar-event-${event.id}`} />)}</div>
            ) : <div className="text-sm text-[color:var(--nova-text-3)]" data-testid="calendar-empty-day">Bu gün için Google Takvim'de etkinlik yok.</div>}
          </section>
        </div>
      </WorkspaceState>
    </div>
  );
}