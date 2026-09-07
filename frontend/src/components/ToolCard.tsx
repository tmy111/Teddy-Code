import { useI18n, type MessageKey } from "../i18n";
import type { TimelineItem } from "../types";

type ToolItem = Extract<TimelineItem, { kind: "tool" }>;

const LABELS: Record<string, MessageKey> = {
  read_file: "toolReadFile",
  list_files: "toolListFiles",
  search: "toolSearch",
  run_shell: "toolRunShell",
  write_file: "toolWriteFile",
  patch_file: "toolPatchFile",
  inspect_image: "toolInspectImage",
  ask_user: "toolAskUser",
  agent: "toolAgent",
};

function primaryArgument(name: string, args: Record<string, unknown>) {
  const key = name === "run_shell" ? "command" : name === "search" ? "pattern" : "path";
  const value = args[key];
  if (typeof value === "string" && value) return value;
  const fallback = Object.values(args).find((item) => typeof item === "string");
  return typeof fallback === "string" ? fallback : "";
}

export function ToolCard({ item }: { item: ToolItem }) {
  const { t } = useI18n();
  const icon = item.status === "running" ? "●" : item.status === "success" ? "✓" : "!";
  const label = LABELS[item.name] ? t(LABELS[item.name]) : item.name.replaceAll("_", " ");
  const detail = primaryArgument(item.name, item.args);
  return (
    <details className={`tool-card ${item.status}`} open={item.status !== "success"}>
      <summary>
        <span className="tool-status" aria-hidden="true">{icon}</span>
        <span className="tool-heading">
          <strong>{label}</strong>
          {detail && <code>{detail}</code>}
        </span>
        <span className="tool-duration">
          {t(item.status === "running" ? "toolRunning" : item.status === "success" ? "toolSuccess" : "toolError")}
        </span>
      </summary>
      {item.content && <pre className="tool-output">{item.content}</pre>}
    </details>
  );
}
