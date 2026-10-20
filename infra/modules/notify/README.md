# notify

SNS topic `nightwatch-notify`, consumed by the `nightwatch-notifier` Lambda.

- **Channels:** ntfy push (HTTPS POST, 3 s timeout) and SES email (sandbox, verified identity). SMS is a documented stub.
- **Message text:** deterministic, built by the publisher (MCP server or escalation Lambda) from incident fields. Never LLM text.
- **Contact lookup:** the notifier fetches contact channels from DynamoDB (`HH#` items), so SNS messages carry no contact details.
- **ntfy topic:** an SSM SecureString (`/nightwatch/ntfy-topic`) whose value comes from gitignored tfvars. The notifier reads it once at init.
- **Email:** creating the SES identity sends a verification email. Until that link is clicked, email delivery fails, but push still works.
