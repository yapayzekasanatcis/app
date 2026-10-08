import { CalendarDays, MapPin, RefreshCw } from "lucide-react";

export const PageHeader = ({ eyebrow, title, source }) => (
  <div className="flex items-end justify-between gap-4 flex-wrap">
    <div>
      <div className="font-mono-nova text-xs uppercase tracking-[0.3em] text-[color:var(--nova-text-3)]">{eyebrow}</div>
      <h1 className="font-serif-display text-4xl md:text-5xl mt-2 text-[color:var(--nova-text)]">{title}</h1>
    </div>
    {source && <div className="font-mono-nova text-[10px] uppercase tracking-widest text-emerald-300" data-testid="page-data-source">{source}</div>}
  </div>
);

export const WorkspaceState = ({ loading, error, empty, onRetry, children, testId }) => {
  if (loading) return <div className="text-[color:var(--nova-text-3)]" data-testid={`${testId}-loading`}>Gerçek veriler yükleniyor…</div>;
  if (error) return (
    <div className="nova-card p-6" data-testid={`${testId}-error`}>
      <div className="text-red-300">Gerçek Google verisi alınamadı: {error}</div>
      <button onClick={onRetry} data-testid={`${testId}-retry`} className="mt-4 inline-flex items-center gap-2 text-sm text-[color:var(--nova-amber)]">
        <RefreshCw className="h-4 w-4" /> Yeniden dene
      </button>
    </div>
  );
  if (empty) return <div className="nova-card p-8 text-sm text-[color:var(--nova-text-3)]" data-testid={`${testId}-empty`}>Bu kaynakta gerçek kayıt bulunmuyor.</div>;
  return children;
};

export const EventItem = ({ event, testId }) => (
  <div className="nova-card p-4 flex items-start gap-4" data-testid={testId}>
    <div className="font-mono-nova text-sm text-[color:var(--nova-amber)] min-w-12 pt-0.5">
      {event.start_time?.includes("T") ? event.start_time.slice(11, 16) : "Tüm gün"}
    </div>
    <div className="min-w-0 flex-1">
      <div className="text-[color:var(--nova-text)]">{event.title}</div>
      {event.location && <div className="mt-1 flex items-start gap-1 text-xs text-[color:var(--nova-text-3)]"><MapPin className="h-3 w-3 mt-0.5 shrink-0" /> {event.location}</div>}
      <div className="mt-2 font-mono-nova text-[10px] uppercase tracking-widest text-[color:var(--nova-text-3)]">Google Calendar</div>
    </div>
  </div>
);

export const TaskItem = ({ task, testId, showRank }) => (
  <div className="nova-card p-4 flex items-start gap-4" data-testid={testId}>
    {showRank && <div className="font-serif-display text-2xl text-[color:var(--nova-amber)]">{showRank}</div>}
    <div className="min-w-0 flex-1">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="text-[color:var(--nova-text)]">{task.title}</div>
        <span className="text-[10px] uppercase tracking-wider text-[color:var(--nova-amber)]">{task.priority_label}</span>
      </div>
      {task.description && <div className="mt-1 text-sm text-[color:var(--nova-text-2)]">{task.description}</div>}
      <div className="mt-2 text-xs text-[color:var(--nova-text-3)]">{task.due_label || "Son tarih belirtilmemiş"} · {task.status}</div>
    </div>
  </div>
);

export const RoutineItem = ({ routine, testId }) => (
  <div className="nova-card p-4" data-testid={testId}>
    <div className="flex items-start justify-between gap-3">
      <div className="text-[color:var(--nova-text)]">{routine.title}</div>
      {routine.time && <div className="font-mono-nova text-xs text-[color:var(--nova-amber)]">{routine.time}</div>}
    </div>
    <div className="mt-1 text-sm text-[color:var(--nova-text-2)]">{routine.schedule}</div>
    {routine.rule && <div className="mt-2 text-xs text-[color:var(--nova-text-3)]">{routine.rule}</div>}
  </div>
);

export const ProjectItem = ({ project, testId }) => (
  <div className="nova-card p-4" data-testid={testId}>
    <div className="flex items-start justify-between gap-3 flex-wrap">
      <div className="text-[color:var(--nova-text)]">{project.title}</div>
      <span className="text-[10px] uppercase tracking-wider text-emerald-300">{project.status}</span>
    </div>
    {project.next_step && <div className="mt-2 text-sm text-[color:var(--nova-text-2)]">Sonraki adım: {project.next_step}</div>}
    {project.period && <div className="mt-2 text-xs text-[color:var(--nova-text-3)]">{project.period}</div>}
  </div>
);

export const SectionTitle = ({ children }) => (
  <div className="flex items-center gap-2 font-mono-nova text-xs uppercase tracking-widest text-[color:var(--nova-text-3)]">
    <CalendarDays className="h-4 w-4 text-[color:var(--nova-amber)]" /> {children}
  </div>
);
