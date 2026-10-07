# Security

## Reporting a vulnerability

Please report vulnerabilities privately to the maintainers (a dedicated address will be
published with the first release). Do not open a public issue. We aim to acknowledge reports
within three working days.

## Security posture

Contxt treats context as sensitive and model output as untrusted.

- **Local-only by default.** The server binds to 127.0.0.1; Docker publishes ports on the
  loopback interface only. Exposing it beyond the machine is an explicit operator choice
  behind a TLS reverse proxy.
- **One revocable credential per connection.** Each model connection has its own token,
  stored only as a SHA-256 hash and shown once. Its grant limits actions and projects. The
  acting identity is always taken from the credential, never from request parameters.
- **Human release gates.** Approving, exporting, changing durable Brain context and
  administering connections can never be granted to a model credential.
- **Untrusted content stays data.** Uploaded files, retrieved pages and model output may
  contain instructions; they are stored and shown as data and never widen a task's authority.
- **Secrets stay out of content.** Tokens live in the environment or the secrets folder of the
  data directory, never in prompts, Brain entries, logs or exported bundles.
- **Auditability.** Every consequential write appends an event with actor, subject, time and
  reason to an append-only log.
- **No telemetry.** Nothing is sent anywhere unless you connect it.
- **Your Brain stays out of this repository.** `brain/`, `data/`, `outputs/` and `.env` are
  ignored by git, and the Brain commits only into its own repository, never into one it
  happens to sit inside.
