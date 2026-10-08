import { useWorkspaceData } from "@/context/WorkspaceDataContext";
import { EventItem, PageHeader, SectionTitle, TaskItem, WorkspaceState } from "@/components/WorkspaceViews";

export default function YarinPage() {
  const { data, loading, error, refresh } = useWorkspaceData();
  const events = data?.tomorrow_events || [];
  const preparations = (data?.priorities || []).slice(0, 3);
  const tomorrow = data?.anchor_date
    ? new Date(`${data.anchor_date}T12:00:00`).setDate(new Date(`${data.anchor_date}T12:00:00`).getDate() + 1)
    : Date.now() + 86400000;
  const label = new Date(tomorrow).toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="space-y-8" data-testid="yarin-page">
      <PageHeader eyebrow="Yarın" title={label} source="Google Calendar · NOVA Özel Takvim" />
      <WorkspaceState loading={loading} error={error} empty={!events.length} onRetry={refresh} testId="tomorrow-events">
        <section className="space-y-3" data-testid="tomorrow-events-list">
          <SectionTitle>Yarının Programı</SectionTitle>
          {events.map(event => <EventItem key={event.id} event={event} testId={`tomorrow-event-${event.id}`} />)}
        </section>
      </WorkspaceState>
      <section className="space-y-3" data-testid="tomorrow-preparations">
        <SectionTitle>Yaklaşan Ön Kontroller</SectionTitle>
        {preparations.map((task, index) => <TaskItem key={task.id} task={task} showRank={index + 1} testId={`tomorrow-task-${task.id}`} />)}
      </section>
    </div>
  );
}