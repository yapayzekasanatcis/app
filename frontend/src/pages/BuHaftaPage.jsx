import { useWorkspaceData } from "@/context/WorkspaceDataContext";
import { PageHeader, WorkspaceState } from "@/components/WorkspaceViews";

const DAYS = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"];

export default function BuHaftaPage() {
  const { data, loading, error, refresh } = useWorkspaceData();
  const days = [];
  if (data?.week_start) {
    const monday = new Date(`${data.week_start}T12:00:00`);
    for (let index = 0; index < 7; index += 1) {
      const current = new Date(monday);
      current.setDate(monday.getDate() + index);
      const key = `${current.getFullYear()}-${String(current.getMonth() + 1).padStart(2, "0")}-${String(current.getDate()).padStart(2, "0")}`;
      days.push({ key, date: current, items: (data.week_events || []).filter(event => event.start_time?.slice(0, 10) === key) });
    }
  }

  return (
    <div className="space-y-8" data-testid="bu-hafta-page">
      <PageHeader eyebrow="Bu Hafta" title="Haftalık Görünüm" source="Google Calendar · NOVA Özel Takvim" />
      <WorkspaceState loading={loading} error={error} empty={!days.length} onRetry={refresh} testId="week-view">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="week-days-grid">
          {days.map(({ key, date, items }) => (
            <section key={key} className="nova-card p-4" data-testid={`week-day-${key}`}>
              <div className="flex items-center justify-between mb-3">
                <div className="font-serif-display text-lg">{DAYS[date.getDay()]}</div>
                <div className="font-mono-nova text-xs text-[color:var(--nova-text-3)]">{date.toLocaleDateString("tr-TR", { day: "numeric", month: "short" })}</div>
              </div>
              {items.length ? (
                <ul className="space-y-2">
                  {items.map(event => (
                    <li key={event.id} className="text-sm" data-testid={`week-event-${event.id}`}>
                      <span className="font-mono-nova text-xs text-[color:var(--nova-amber)] mr-2">{event.start_time?.includes("T") ? event.start_time.slice(11, 16) : "Tüm gün"}</span>
                      <span className="text-[color:var(--nova-text)]">{event.title}</span>
                    </li>
                  ))}
                </ul>
              ) : <div className="text-xs text-[color:var(--nova-text-3)]">Google Takvim'de kayıt yok</div>}
            </section>
          ))}
        </div>
      </WorkspaceState>
    </div>
  );
}