import { useI18n, type MessageKey } from "../i18n";

export function RuntimeNotice({
  content,
  translationKey,
  tone,
}: {
  content: string;
  translationKey?: MessageKey;
  tone: "neutral" | "warning" | "error";
}) {
  const { t } = useI18n();

  return (
    <div className={`runtime-notice ${tone}`} role={tone === "error" ? "alert" : "status"}>
      <span aria-hidden="true">{tone === "error" ? "!" : tone === "warning" ? "△" : "·"}</span>
      <span>{translationKey ? t(translationKey) : content}</span>
    </div>
  );
}
