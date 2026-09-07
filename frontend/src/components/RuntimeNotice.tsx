export function RuntimeNotice({
  content,
  tone,
}: {
  content: string;
  tone: "neutral" | "warning" | "error";
}) {
  return (
    <div className={`runtime-notice ${tone}`} role={tone === "error" ? "alert" : "status"}>
      <span aria-hidden="true">{tone === "error" ? "!" : tone === "warning" ? "△" : "·"}</span>
      <span>{content}</span>
    </div>
  );
}
