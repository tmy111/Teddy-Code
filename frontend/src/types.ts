import type { MessageKey } from "./i18n";

export interface WorkspaceInfo {
  cwd: string;
  repo_root: string;
  branch: string;
}

export interface SessionSummary {
  id: string;
  created_at: string;
  updated_at: string;
  history_count: number;
  runtime_mode: string;
  workspace_root: string;
  last_final_answer: string;
  model: string;
  active: boolean;
}

export interface HistoryItem {
  event_id?: string;
  role: string;
  content?: string;
  name?: string;
  args?: Record<string, unknown>;
  tool_status?: string;
}

export interface SessionDetail extends SessionSummary {
  history: HistoryItem[];
}

export interface RuntimeEvent {
  type: string;
  run_id?: string;
  task_id?: string;
  name?: string;
  args?: Record<string, unknown>;
  content?: string;
  metadata?: Record<string, unknown>;
  attempts?: number;
  tool_steps?: number;
  kind?: string;
  request_id?: string;
  question?: string;
  choices?: string[];
  error_type?: string;
}

export type TimelineItem =
  | {
      id: string;
      kind: "message";
      role: "user" | "assistant";
      content: string;
      stopped?: boolean;
    }
  | {
      id: string;
      kind: "tool";
      name: string;
      args: Record<string, unknown>;
      content: string;
      status: "running" | "success" | "error";
    }
  | {
      id: string;
      kind: "notice";
      content: string;
      translationKey?: MessageKey;
      tone: "neutral" | "warning" | "error";
    }
  | {
      id: string;
      kind: "interaction";
      interaction: "approval" | "question";
      requestId: string;
      title: string;
      actionName?: string;
      args?: Record<string, unknown>;
      choices?: string[];
      resolved?: string;
    };
