import type { KeyboardEvent } from "react";
import { useI18n } from "../i18n";

export function Composer({
  value,
  running,
  ready,
  onChange,
  onSend,
  onStop,
}: {
  value: string;
  running: boolean;
  ready: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
}) {
  const { t } = useI18n();
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!running && value.trim()) onSend();
    }
  };
  return (
    <div className="composer-wrap">
      <div className={`composer ${running ? "running" : ""}`}>
        <textarea
          aria-label={t("composerLabel")}
          value={value}
          disabled={!ready || running}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={ready ? t("composerPlaceholder") : t("composerPreparing")}
          rows={2}
        />
        <div className="composer-footer">
          <span>{t("composerHint")}</span>
          {running ? (
            <button className="button stop" onClick={onStop}><span aria-hidden="true">■</span> {t("stop")}</button>
          ) : (
            <button className="button send" disabled={!ready || !value.trim()} onClick={onSend}>{t("send")} <span aria-hidden="true">↗</span></button>
          )}
        </div>
      </div>
    </div>
  );
}
