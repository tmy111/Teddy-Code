import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useI18n } from "../i18n";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  stopped?: boolean;
}

export function ChatMessage({ role, content, stopped }: ChatMessageProps) {
  const { t } = useI18n();

  return (
    <article className={`chat-message ${role} ${stopped ? "stopped" : ""}`}>
      <div className="message-label">
        <span>{role === "user" ? t("you") : t("teddy")}</span>
        {stopped && <span className="message-state">{t("stopped")}</span>}
      </div>
      <div className="markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </article>
  );
}
