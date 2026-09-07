import type { SessionSummary } from "../types";

function sessionLabel(session: SessionSummary) {
  return session.last_final_answer || `Session ${session.id.slice(-6)}`;
}

function sessionTime(session: SessionSummary) {
  const value = session.updated_at || session.created_at;
  if (!value) return "Just now";
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? "Recent"
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

export function SessionSidebar({
  sessions,
  selectedId,
  disabled,
  onSelect,
  onCreate,
}: {
  sessions: SessionSummary[];
  selectedId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
}) {
  return (
    <aside className="session-sidebar">
      <div className="brand-row">
        <div className="brand-mark">T</div>
        <div>
          <div className="brand-name">TeddyCode</div>
          <div className="brand-meta">local agent</div>
        </div>
      </div>
      <button className="new-session" onClick={onCreate} disabled={disabled}>
        <span aria-hidden="true">＋</span> New session
      </button>
      <div className="sidebar-heading">Sessions</div>
      <nav className="session-list" aria-label="Sessions">
        {sessions.map((session) => (
          <button
            key={session.id}
            className={`session-item ${session.id === selectedId ? "selected" : ""}`}
            onClick={() => onSelect(session.id)}
            disabled={disabled}
          >
            <span className="session-title">{sessionLabel(session)}</span>
            <span className="session-meta">
              <span>{sessionTime(session)}</span>
              <span>{session.history_count} events</span>
            </span>
          </button>
        ))}
      </nav>
      <div className="local-badge"><span /> Local only</div>
    </aside>
  );
}
