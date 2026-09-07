import { useState } from "react";
import { useI18n } from "../i18n";
import type { TimelineItem } from "../types";

type InteractionItem = Extract<TimelineItem, { kind: "interaction" }>;

export function InteractionCard({
  item,
  onResolve,
}: {
  item: InteractionItem;
  onResolve: (answer: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const resolve = async (value: string) => {
    setBusy(true);
    setError("");
    try {
      await onResolve(value);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("errorSubmitResponse"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`interaction-card ${item.resolved ? "resolved" : ""}`}>
      <div className="interaction-kicker">
        {item.interaction === "approval" ? t("approvalRequired") : t("teddyQuestion")}
      </div>
      <h3>
        {item.interaction === "approval"
          ? t("approvalTitle", { action: item.actionName || t("thisAction") })
          : item.title || t("questionFallback")}
      </h3>
      {item.args && <pre>{JSON.stringify(item.args, null, 2)}</pre>}
      {item.resolved ? (
        <div className="interaction-resolution">{t("answered", { answer: item.resolved })}</div>
      ) : item.interaction === "approval" ? (
        <div className="interaction-actions">
          <button className="button secondary" disabled={busy} onClick={() => resolve("deny")}>{t("deny")}</button>
          <button className="button primary" disabled={busy} onClick={() => resolve("allow")}>{t("allow")}</button>
        </div>
      ) : (
        <div className="question-controls">
          {!!item.choices?.length && (
            <div className="choice-list">
              {item.choices.map((choice) => (
                <button className="choice" disabled={busy} key={choice} onClick={() => resolve(choice)}>{choice}</button>
              ))}
            </div>
          )}
          <div className="answer-row">
            <input value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder={t("typeAnswer")} />
            <button className="button primary" disabled={busy || !answer.trim()} onClick={() => resolve(answer.trim())}>{t("reply")}</button>
          </div>
        </div>
      )}
      {error && <div className="interaction-error" role="alert">{error}</div>}
    </section>
  );
}
