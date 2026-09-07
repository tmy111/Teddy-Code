import type { SessionSummary } from "../types";
import { useI18n } from "../i18n";

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
  const { language, t } = useI18n();
  const sessionLabel = (session: SessionSummary) => (
    session.last_final_answer || t("sessionFallback", { id: session.id.slice(-6) })
  );
  const sessionTime = (session: SessionSummary) => {
    const value = session.updated_at || session.created_at;
    if (!value) return t("justNow");
    const date = new Date(value);
    return Number.isNaN(date.valueOf())
      ? t("recent")
      : new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en", { month: "short", day: "numeric" }).format(date);
  };

  return (
    <aside className="session-sidebar">
      <div className="brand-row">
        <div className="brand-mark">T</div>
        <div>
          <div className="brand-name">TeddyCode</div>
          <div className="brand-meta">{t("localAgent")}</div>
        </div>
      </div>
      <button className="new-session" onClick={onCreate} disabled={disabled}>
        <span aria-hidden="true">＋</span> {t("newSession")}
      </button>
      <div className="sidebar-heading">{t("sessions")}</div>
      <nav className="session-list" aria-label={t("sessions")}>
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
              <span>{t(session.history_count === 1 ? "eventCountOne" : "eventCount", { count: session.history_count })}</span>
            </span>
          </button>
        ))}
      </nav>
      <div className="local-badge"><span /> {t("localOnly")}</div>
    </aside>
  );
}
