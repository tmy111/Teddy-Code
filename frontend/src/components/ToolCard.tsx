import type { TimelineItem } from "../types";

type ToolItem = Extract<TimelineItem, { kind: "tool" }>;

const LABELS: Record<string, string> = {
  read_file: "Read file",
  list_files: "List files",
  search: "Search workspace",
  run_shell: "Run command",
  write_file: "Write file",
  patch_file: "Patch file",
  inspect_image: "Inspect image",
  ask_user: "Ask user",
  agent: "Run sub-agent",
};

function primaryArgument(name: string, args: Record<string, unknown>) {
  const key = name === "run_shell" ? "command" : name === "search" ? "pattern" : "path";
  const value = args[key];
  if (typeof value === "string" && value) return value;
  const fallback = Object.values(args).find((item) => typeof item === "string");
  return typeof fallback === "string" ? fallback : "";
}

export function ToolCard({ item }: { item: ToolItem }) {
  const icon = item.status === "running" ? "●" : item.status === "success" ? "✓" : "!";
  const label = LABELS[item.name] || item.name.replaceAll("_", " ");
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
          {item.status === "running" ? "running" : item.status}
        </span>
      </summary>
      {item.content && <pre className="tool-output">{item.content}</pre>}
    </details>
  );
}
