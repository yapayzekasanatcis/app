import { useWorkspaceData } from "@/context/WorkspaceDataContext";
import {
  EventItem, PageHeader, ProjectItem, RoutineItem, SectionTitle, TaskItem, WorkspaceState,
} from "@/components/WorkspaceViews";

const DataPage = ({ eyebrow, title, source, items, loading, error, refresh, testId, renderItem }) => (
  <div className="space-y-8" data-testid={testId}>
    <PageHeader eyebrow={eyebrow} title={title} source={source} />
    <WorkspaceState loading={loading} error={error} empty={!items.length} onRetry={refresh} testId={`${testId}-data`}>
      <div className="space-y-3">{items.map(renderItem)}</div>
    </WorkspaceState>
  </div>
);

export const BekleyenIslerPage = () => {
  const workspace = useWorkspaceData();
  const items = workspace.data?.pending_tasks || [];
  return <DataPage {...workspace} items={items} eyebrow="Tüm Aktif Görevler" title="Bekleyen İşler" source="Google Sheets · İşler" testId="bekleyen-isler-page" renderItem={task => <TaskItem key={task.id} task={task} testId={`pending-task-${task.id}`} />} />;
};

export const OnceliklerPage = () => {
  const workspace = useWorkspaceData();
  const items = workspace.data?.priorities || [];
  return <DataPage {...workspace} items={items} eyebrow="Yakın Tarih ve Bağımlılıklar" title="Öncelikler" source="Google Sheets · İşler + Projeler" testId="oncelikler-page" renderItem={(task, index) => <TaskItem key={task.id} task={task} showRank={index + 1} testId={`priority-task-${task.id}`} />} />;
};

export const KomagenePage = () => {
  const workspace = useWorkspaceData();
  const items = workspace.data?.komagene?.routines || [];
  return <DataPage {...workspace} items={items} eyebrow="İşletme Operasyonu" title="Komagene" source="Google Sheets · Rutinler" testId="komagene-page" renderItem={routine => <RoutineItem key={routine.id} routine={routine} testId={`komagene-routine-${routine.id}`} />} />;
};

export const BoraAIStudyoPage = () => {
  const workspace = useWorkspaceData();
  const items = workspace.data?.bora_ai?.projects || [];
  return <DataPage {...workspace} items={items} eyebrow="Aktif ve Bekleyen Projeler" title="Bora AI Stüdyo" source="Google Sheets · Projeler" testId="bora-ai-page" renderItem={project => <ProjectItem key={project.id} project={project} testId={`bora-ai-project-${project.id}`} />} />;
};

export const KisiselPage = () => {
  const workspace = useWorkspaceData();
  const items = workspace.data?.personal?.items || [];
  return <DataPage {...workspace} items={items} eyebrow="Özel Yaşam" title="Kişisel" source="Google Workspace" testId="kisisel-page" renderItem={item => item.next_step
    ? <ProjectItem key={item.id} project={item} testId={`personal-project-${item.id}`} />
    : item.start_time
      ? <EventItem key={item.id} event={item} testId={`personal-event-${item.id}`} />
    : item.schedule
      ? <RoutineItem key={item.id} routine={item} testId={`personal-routine-${item.id}`} />
      : <TaskItem key={item.id} task={item} testId={`personal-task-${item.id}`} />} />;
};

export const TiyatralNikahPage = () => {
  const { data, loading, error, refresh } = useWorkspaceData();
  const events = data?.tiyatral?.events || [];
  const tasks = data?.tiyatral?.tasks || [];
  return (
    <div className="space-y-8" data-testid="tiyatral-nikah-page">
      <PageHeader eyebrow="Organizasyonlar ve Hazırlıklar" title="Tiyatral Nikâh" source="Google Calendar + Google Sheets" />
      <WorkspaceState loading={loading} error={error} empty={!events.length && !tasks.length} onRetry={refresh} testId="tiyatral-data">
        <section className="space-y-3" data-testid="tiyatral-events-list">
          <SectionTitle>Takvim Programı</SectionTitle>
          {events.map(event => <EventItem key={event.id} event={event} testId={`tiyatral-event-${event.id}`} />)}
        </section>
        {tasks.length > 0 && (
          <section className="space-y-3 mt-8" data-testid="tiyatral-tasks-list">
            <SectionTitle>Bekleyen Hazırlıklar</SectionTitle>
            {tasks.map(task => <TaskItem key={task.id} task={task} testId={`tiyatral-task-${task.id}`} />)}
          </section>
        )}
      </WorkspaceState>
    </div>
  );
};