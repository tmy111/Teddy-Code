import type {
  RuntimeEvent,
  SessionDetail,
  SessionSummary,
  WorkspaceInfo,
} from "./types";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  workspace: () => requestJson<WorkspaceInfo>("/api/workspace"),
  sessions: () => requestJson<SessionSummary[]>("/api/sessions"),
  session: (id: string) =>
    requestJson<SessionDetail>(`/api/sessions/${encodeURIComponent(id)}`),
  createSession: () =>
    requestJson<SessionDetail>("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),
  abort: (id: string) =>
    requestJson<{ aborted: boolean }>(
      `/api/sessions/${encodeURIComponent(id)}/abort`,
      { method: "POST" },
    ),
  resolveApproval: (sessionId: string, requestId: string, decision: string) =>
    requestJson<{ status: string }>(
      `/api/sessions/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(requestId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      },
    ),
  resolveQuestion: (sessionId: string, requestId: string, answer: string) =>
    requestJson<{ status: string }>(
      `/api/sessions/${encodeURIComponent(sessionId)}/questions/${encodeURIComponent(requestId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
      },
    ),
};

export async function streamMessage(
  sessionId: string,
  message: string,
  onEvent: (event: RuntimeEvent) => void,
): Promise<void> {
  const response = await fetch(
    `/api/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    },
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail || `Message failed (${response.status})`);
  }
  if (!response.body) throw new Error("Streaming response is unavailable.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const data = frame
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) onEvent(JSON.parse(data) as RuntimeEvent);
    }
    if (done) break;
  }
}
