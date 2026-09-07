import { useEffect, useRef, useState } from "react";
import { api, streamMessage } from "./api";
import { ChatMessage } from "./components/ChatMessage";
import { Composer } from "./components/Composer";
import { InteractionCard } from "./components/InteractionCard";
import { RuntimeNotice } from "./components/RuntimeNotice";
import { SessionSidebar } from "./components/SessionSidebar";
import { ToolCard } from "./components/ToolCard";
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
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selected, setSelected] = useState<SessionDetail | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const refreshSessions = async () => setSessions(await api.sessions());

  const openSession = async (id: string) => {
    setError("");
    const detail = await api.session(id);
    setSelected(detail);
    setItems(historyToTimeline(detail.history));
  };

  const createSession = async () => {
    if (running) return;
    setError("");
    try {
      const detail = await api.createSession();
      setSelected(detail);
      setItems([]);
      await refreshSessions();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create a session.");
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
        if (active) setError(cause instanceof Error ? cause.message : "Could not connect to TeddyCode.");
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
      setStatus("Agent started");
      setItems((current) => [...current, { id: nextId("start"), kind: "notice", content: "Agent started", tone: "neutral" }]);
      return;
    }
    if (event.type === "model_requested") {
      setStatus(`Thinking · pass ${event.attempts || 1}`);
      return;
    }
    if (event.type === "model_parsed") {
      setStatus(event.kind === "final" ? "Preparing answer" : "Planning next action");
      return;
    }
    if (event.type === "tool_call") {
      setStatus(`Running ${event.name || "tool"}`);
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
      setStatus("Thinking after tool");
      return;
    }
    if (event.type === "approval_required") {
      setStatus("Waiting for approval");
      setItems((current) => [...current, {
        id: nextId("approval"), kind: "interaction", interaction: "approval",
        requestId: event.request_id || "", title: `Allow ${event.name || "this action"}?`, args: event.args,
      }]);
      return;
    }
    if (event.type === "question_required") {
      setStatus("Waiting for your answer");
      setItems((current) => [...current, {
        id: nextId("question"), kind: "interaction", interaction: "question",
        requestId: event.request_id || "", title: event.question || "Teddy needs more information", choices: event.choices,
      }]);
      return;
    }
    if (event.type === "final" || event.type === "stop") {
      setItems((current) => [...current, {
        id: nextId("answer"), kind: "message", role: "assistant",
        content: event.content || "", stopped: event.type === "stop",
      }]);
      setStatus(event.type === "stop" ? "Stopped" : "Complete");
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
        id: nextId("error"), kind: "notice", content: event.content || "The turn failed.", tone: "error",
      }]);
      setStatus("Error");
    }
  };

  const send = async () => {
    const message = prompt.trim();
    const sessionId = selected?.id;
    if (!message || !sessionId || running) return;
    setPrompt("");
    setError("");
    setRunning(true);
    setStatus("Starting");
    setItems((current) => [...current, { id: nextId("user"), kind: "message", role: "user", content: message }]);
    try {
      await streamMessage(sessionId, message, handleEvent);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "The stream ended unexpectedly.";
      setError(message);
      setItems((current) => [...current, { id: nextId("stream-error"), kind: "notice", content: message, tone: "error" }]);
      setStatus("Error");
    } finally {
      setRunning(false);
      await refreshSessions().catch(() => undefined);
    }
  };

  const stop = async () => {
    if (!selected) return;
    setStatus("Stopping");
    try {
      await api.abort(selected.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not stop the turn.");
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
    setStatus("Continuing");
  };

  return (
    <div className="app-shell">
      <SessionSidebar
        sessions={sessions}
        selectedId={selected?.id || null}
        disabled={running}
        onSelect={(id) => openSession(id).catch((cause) => setError(String(cause)))}
        onCreate={createSession}
      />
      <main className="workspace-panel">
        <header className="topbar">
          <div>
            <div className="workspace-name">{workspace ? shortPath(workspace.repo_root) : "TeddyCode workspace"}</div>
            <div className="workspace-branch"><span>⌁</span> {workspace?.branch || "local"}</div>
          </div>
          <div className="runtime-pills">
            <span className={`run-state ${running ? "active" : ""}`}><i />{status}</span>
            <span className="model-pill">{selected?.model || "configured model"}</span>
          </div>
        </header>
        <section className="conversation" aria-live="polite">
          <div className="conversation-inner">
            {loading ? (
              <div className="empty-state"><div className="empty-mark pulse">T</div><h2>Opening workspace</h2></div>
            ) : !items.length ? (
              <div className="empty-state">
                <div className="empty-mark">T</div>
                <h1>What should we work on?</h1>
                <p>Teddy can inspect this repository, run tools, and make changes with your approval.</p>
                <div className="suggestion-row">
                  {["Map the project structure", "Find risky code paths", "Run the test suite"].map((text) => (
                    <button key={text} onClick={() => setPrompt(text)}>{text}</button>
                  ))}
                </div>
              </div>
            ) : (
              items.map((item) => {
                if (item.kind === "message") return <ChatMessage key={item.id} role={item.role} content={item.content} stopped={item.stopped} />;
                if (item.kind === "tool") return <ToolCard key={item.id} item={item} />;
                if (item.kind === "notice") return <RuntimeNotice key={item.id} content={item.content} tone={item.tone} />;
                return <InteractionCard key={item.id} item={item} onResolve={(value) => resolveInteraction(item, value)} />;
              })
            )}
            {running && <div className="thinking-line"><span /><span /><span /><em>{status}</em></div>}
            {error && <RuntimeNotice content={error} tone="error" />}
            <div ref={endRef} />
          </div>
        </section>
        <Composer value={prompt} running={running} ready={!!selected && !loading} onChange={setPrompt} onSend={send} onStop={stop} />
      </main>
    </div>
  );
}
