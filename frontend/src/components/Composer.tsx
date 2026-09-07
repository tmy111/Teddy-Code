import type { KeyboardEvent } from "react";

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
          aria-label="Message TeddyCode"
          value={value}
          disabled={!ready || running}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={ready ? "Ask Teddy to inspect, explain, or change this workspace…" : "Preparing workspace…"}
          rows={2}
        />
        <div className="composer-footer">
          <span>Enter to send · Shift+Enter for a new line</span>
          {running ? (
            <button className="button stop" onClick={onStop}><span aria-hidden="true">■</span> Stop</button>
          ) : (
            <button className="button send" disabled={!ready || !value.trim()} onClick={onSend}>Send <span aria-hidden="true">↗</span></button>
          )}
        </div>
      </div>
    </div>
  );
}
