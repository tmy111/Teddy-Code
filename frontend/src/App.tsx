import { useEffect, useRef, useState } from "react";
import { api, streamMessage } from "./api";
import { ChatMessage } from "./components/ChatMessage";
import { Composer } from "./components/Composer";
import { InteractionCard } from "./components/InteractionCard";
import { LanguageToggle } from "./components/LanguageToggle";
import { RuntimeNotice } from "./components/RuntimeNotice";
import { SessionSidebar } from "./components/SessionSidebar";
import { ToolCard } from "./components/ToolCard";
import { useI18n, type MessageKey, type TranslationValues } from "./i18n";
import type {
  HistoryItem,
  RuntimeEvent,
  SessionDetail,
  SessionSummary,
  TimelineItem,
  WorkspaceInfo,
} from "./types";

let localId = 0;
const nextId = (prefix: string) => `${prefix}-${++localId}`;

interface LocalizedMessage {
  key: MessageKey;
  values?: TranslationValues;
}

const localized = (key: MessageKey, values?: TranslationValues): LocalizedMessage => ({ key, values });

function errorMessage(cause: unknown, fallback: MessageKey): string | LocalizedMessage {
  return cause instanceof Error ? cause.message : localized(fallback);
}

function historyToTimeline(history: HistoryItem[]): TimelineItem[] {
  return history.flatMap((item, index): TimelineItem[] => {
    const id = item.event_id || `history-${index}`;
    if (item.role === "user" || item.role === "assistant") {
      return [{ id, kind: "message", role: item.role, content: item.content || "" }];
    }
    if (item.role === "tool") {
      const failed = ["error", "rejected", "partial_success"].includes(item.tool_status || "");
      return [{
        id,
        kind: "tool",
        name: item.name || "tool",
        args: item.args || {},
        content: item.content || "",
        status: failed ? "error" : "success",
      }];
    }
    return [];
  });
}

function shortPath(path: string) {
  const parts = path.replaceAll("\\", "/").split("/").filter(Boolean);
  return parts.length > 3 ? `…/${parts.slice(-3).join("/")}` : path;
}

export default function App() {
  const { t } = useI18n();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selected, setSelected] = useState<SessionDetail | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<LocalizedMessage>(() => localized("statusReady"));
  const [error, setError] = useState<string | LocalizedMessage | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const statusText = t(status.key, status.values);
  const visibleError = typeof error === "string" ? error : error ? t(error.key, error.values) : "";

  const refreshSessions = async () => setSessions(await api.sessions());

  const openSession = async (id: string) => {
    setError(null);
    const detail = await api.session(id);
    setSelected(detail);
    setItems(historyToTimeline(detail.history));
  };

  const createSession = async () => {
    if (running) return;
    setError(null);
    try {
      const detail = await api.createSession();
      setSelected(detail);
      setItems([]);
      await refreshSessions();
    } catch (cause) {
      setError(errorMessage(cause, "errorCreateSession"));
    }
  };

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [workspaceInfo, rows] = await Promise.all([api.workspace(), api.sessions()]);
        if (!active) return;
        setWorkspace(workspaceInfo);
        setSessions(rows);
        const detail = rows.length ? await api.session(rows[0].id) : await api.createSession();
        if (!active) return;
        setSelected(detail);
        setItems(historyToTimeline(detail.history));
        if (!rows.length) await refreshSessions();
      } catch (cause) {
        if (active) setError(errorMessage(cause, "errorConnect"));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: running ? "smooth" : "instant", block: "end" });
  }, [items, running]);

  const handleEvent = (event: RuntimeEvent) => {
    if (event.type === "turn_started") {
      setStatus(localized("statusAgentStarted"));
      setItems((current) => [...current, {
        id: nextId("start"), kind: "notice", content: "", translationKey: "statusAgentStarted", tone: "neutral",
      }]);
      return;
    }
    if (event.type === "model_requested") {
      setStatus(localized("statusThinkingPass", { attempt: event.attempts || 1 }));
      return;
    }
    if (event.type === "model_parsed") {
      setStatus(localized(event.kind === "final" ? "statusPreparingAnswer" : "statusPlanningAction"));
      return;
    }
    if (event.type === "tool_call") {
      setStatus(localized("statusRunningTool", { tool: event.name || "tool" }));
      setItems((current) => [...current, {
        id: nextId("tool"),
        kind: "tool",
        name: event.name || "tool",
        args: event.args || {},
        content: "",
        status: "running",
      }]);
      return;
    }
    if (event.type === "tool_result") {
      setItems((current) => {
        const copy = [...current];
        let index = -1;
        for (let position = copy.length - 1; position >= 0; position -= 1) {
          const item = copy[position];
          if (item.kind === "tool" && item.name === event.name && item.status === "running") {
            index = position;
            break;
          }
        }
        const toolStatus = String(event.metadata?.tool_status || "ok");
        const status = ["error", "rejected", "partial_success"].includes(toolStatus) ? "error" : "success";
        const candidate = copy[index];
        if (candidate?.kind === "tool") {
          copy[index] = { ...candidate, content: event.content || "", status };
        }
        return copy;
      });
      setStatus(localized("statusThinkingAfterTool"));
      return;
    }
    if (event.type === "approval_required") {
      setStatus(localized("statusWaitingApproval"));
      setItems((current) => [...current, {
        id: nextId("approval"), kind: "interaction", interaction: "approval",
        requestId: event.request_id || "", title: "", actionName: event.name, args: event.args,
      }]);
      return;
    }
    if (event.type === "question_required") {
      setStatus(localized("statusWaitingAnswer"));
      setItems((current) => [...current, {
        id: nextId("question"), kind: "interaction", interaction: "question",
        requestId: event.request_id || "", title: event.question || "", choices: event.choices,
      }]);
      return;
    }
    if (event.type === "final" || event.type === "stop") {
      setItems((current) => [...current, {
        id: nextId("answer"), kind: "message", role: "assistant",
        content: event.content || "", stopped: event.type === "stop",
      }]);
      setStatus(localized(event.type === "stop" ? "statusStopped" : "statusComplete"));
      return;
    }
    if (["retry", "runtime_notice", "worker_notification"].includes(event.type)) {
      setItems((current) => [...current, {
        id: nextId("notice"), kind: "notice", content: event.content || event.type,
        tone: event.type === "retry" ? "warning" : "neutral",
      }]);
      return;
    }
    if (event.type === "error") {
      setItems((current) => [...current, {
        id: nextId("error"), kind: "notice", content: event.content || "",
        translationKey: event.content ? undefined : "errorTurnFailed", tone: "error",
      }]);
      setStatus(localized("statusError"));
    }
  };

  const send = async () => {
    const message = prompt.trim();
    const sessionId = selected?.id;
    if (!message || !sessionId || running) return;
    setPrompt("");
    setError(null);
    setRunning(true);
    setStatus(localized("statusStarting"));
    setItems((current) => [...current, { id: nextId("user"), kind: "message", role: "user", content: message }]);
    try {
      await streamMessage(sessionId, message, handleEvent);
    } catch (cause) {
      const failure = errorMessage(cause, "errorStream");
      setError(failure);
      setItems((current) => [...current, {
        id: nextId("stream-error"), kind: "notice",
        content: typeof failure === "string" ? failure : "",
        translationKey: typeof failure === "string" ? undefined : failure.key,
        tone: "error",
      }]);
      setStatus(localized("statusError"));
    } finally {
      setRunning(false);
      await refreshSessions().catch(() => undefined);
    }
  };

  const stop = async () => {
    if (!selected) return;
    setStatus(localized("statusStopping"));
    try {
      await api.abort(selected.id);
    } catch (cause) {
      setError(errorMessage(cause, "errorStop"));
    }
  };

  const resolveInteraction = async (item: Extract<TimelineItem, { kind: "interaction" }>, value: string) => {
    if (!selected) return;
    if (item.interaction === "approval") {
      await api.resolveApproval(selected.id, item.requestId, value);
    } else {
      await api.resolveQuestion(selected.id, item.requestId, value);
    }
    setItems((current) => current.map((candidate) => candidate.id === item.id ? { ...candidate, resolved: value } : candidate));
    setStatus(localized("statusContinuing"));
  };

  return (
    <div className="app-shell">
      <SessionSidebar
        sessions={sessions}
        selectedId={selected?.id || null}
        disabled={running}
        onSelect={(id) => openSession(id).catch((cause) => setError(errorMessage(cause, "errorOpenSession")))}
        onCreate={createSession}
      />
      <main className="workspace-panel">
        <header className="topbar">
          <div>
            <div className="workspace-name">{workspace ? shortPath(workspace.repo_root) : t("workspaceFallback")}</div>
            <div className="workspace-branch"><span>⌁</span> {workspace?.branch || t("local")}</div>
          </div>
          <div className="runtime-pills">
            <LanguageToggle />
            <span className={`run-state ${running ? "active" : ""}`}><i />{statusText}</span>
            <span className="model-pill">{selected?.model || t("configuredModel")}</span>
          </div>
        </header>
        <section className="conversation" aria-live="polite">
          <div className="conversation-inner">
            {loading ? (
              <div className="empty-state"><div className="empty-mark pulse">T</div><h2>{t("openingWorkspace")}</h2></div>
            ) : !items.length ? (
              <div className="empty-state">
                <div className="empty-mark">T</div>
                <h1>{t("emptyTitle")}</h1>
                <p>{t("emptyDescription")}</p>
                <div className="suggestion-row">
                  {(["suggestionMap", "suggestionRisks", "suggestionTests"] as MessageKey[]).map((key) => (
                    <button key={key} onClick={() => setPrompt(t(key))}>{t(key)}</button>
                  ))}
                </div>
              </div>
            ) : (
              items.map((item) => {
                if (item.kind === "message") return <ChatMessage key={item.id} role={item.role} content={item.content} stopped={item.stopped} />;
                if (item.kind === "tool") return <ToolCard key={item.id} item={item} />;
                if (item.kind === "notice") return <RuntimeNotice key={item.id} content={item.content} translationKey={item.translationKey} tone={item.tone} />;
                return <InteractionCard key={item.id} item={item} onResolve={(value) => resolveInteraction(item, value)} />;
              })
            )}
            {running && <div className="thinking-line"><span /><span /><span /><em>{statusText}</em></div>}
            {visibleError && <RuntimeNotice content={visibleError} tone="error" />}
            <div ref={endRef} />
          </div>
        </section>
        <Composer value={prompt} running={running} ready={!!selected && !loading} onChange={setPrompt} onSend={send} onStop={stop} />
      </main>
    </div>
  );
}
