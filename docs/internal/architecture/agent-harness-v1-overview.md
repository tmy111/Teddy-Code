# Agent Harness v1 Overview

Agent Harness v1 is Pico's minimal control surface for turning a user request
into a verifiable local session.

The runtime keeps task state explicit: every turn gets a run id, task id,
attempt count, tool step count, stop reason, and final answer. That task state
is written beside the run trace so failures can be inspected after the process
exits.

The harness has five stable boundaries:

- Engine: owns the model/tool/final-answer loop.
- Provider: exposes a single text completion contract.
- Tools: enforce workspace paths, approval policy, and write safety.
- Session event bus: records the user-visible session timeline.
- Plan mode: constrains planning turns to the active plan artifact before
  allowing a final answer.
- Worker manager: owns bounded subagent lifecycle. `Explore` is read-only;
  `worker` can write only inside its declared write scope and reports completion
  through session notifications.
