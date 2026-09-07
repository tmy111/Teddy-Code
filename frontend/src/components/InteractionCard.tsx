import { useState } from "react";
import type { TimelineItem } from "../types";

type InteractionItem = Extract<TimelineItem, { kind: "interaction" }>;

export function InteractionCard({
  item,
  onResolve,
}: {
  item: InteractionItem;
  onResolve: (answer: string) => Promise<void>;
}) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const resolve = async (value: string) => {
    setBusy(true);
    setError("");
    try {
      await onResolve(value);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not submit the response.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`interaction-card ${item.resolved ? "resolved" : ""}`}>
      <div className="interaction-kicker">
        {item.interaction === "approval" ? "Approval required" : "Teddy has a question"}
      </div>
      <h3>{item.title}</h3>
      {item.args && <pre>{JSON.stringify(item.args, null, 2)}</pre>}
      {item.resolved ? (
        <div className="interaction-resolution">Answered: {item.resolved}</div>
      ) : item.interaction === "approval" ? (
        <div className="interaction-actions">
          <button className="button secondary" disabled={busy} onClick={() => resolve("deny")}>Deny</button>
          <button className="button primary" disabled={busy} onClick={() => resolve("allow")}>Allow</button>
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
            <input value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Type an answer" />
            <button className="button primary" disabled={busy || !answer.trim()} onClick={() => resolve(answer.trim())}>Reply</button>
          </div>
        </div>
      )}
      {error && <div className="interaction-error" role="alert">{error}</div>}
    </section>
  );
}
