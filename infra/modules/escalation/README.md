# escalation

When the incident builder creates an incident at or above the policy's severity (high by
default, replays included), it creates a one-time EventBridge Scheduler schedule
`nw-esc-<incident id>`.

- **When it fires:** at `max(started_at, now) + ack_timeout_s`, with `ActionAfterCompletion=DELETE`.
- **What it does:** it invokes `nightwatch-escalation`, which re-reads the incident. If the incident is acknowledged, resolved or ended, it does nothing. Otherwise it changes the status from open to escalated (a conditional update), publishes the escalation message to SNS, and writes an `escalated` timeline event.
- **Acknowledging** doesn't touch Scheduler: the timer fires and does nothing. The MCP server never calls Scheduler.
- **IAM:** the builder gets `scheduler:CreateSchedule` on `schedule/default/nw-esc-*`, plus `iam:PassRole` on `scheduler_role_arn`.
