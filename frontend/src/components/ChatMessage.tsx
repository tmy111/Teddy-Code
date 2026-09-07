import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  stopped?: boolean;
}

export function ChatMessage({ role, content, stopped }: ChatMessageProps) {
  return (
    <article className={`chat-message ${role} ${stopped ? "stopped" : ""}`}>
      <div className="message-label">
        <span>{role === "user" ? "You" : "Teddy"}</span>
        {stopped && <span className="message-state">stopped</span>}
      </div>
      <div className="markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </article>
  );
}
