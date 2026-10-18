# Security Policy

## Supported versions

Only the latest release on `main` receives fixes.

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on this repository. Do not open a public issue for security problems.

Useful reports include a bypass of the file-scope guard, dispatch gate, signed gate files or secrets policy, or any path that lets an agent approve its own human gate. Include the host version, a minimal reproduction and the expected versus actual behaviour.

You can expect an acknowledgement within 7 days. This is a one-maintainer project, so fix timelines are best effort.

## Scope and honest limits

The runtime enforces policy through host hooks; it is not an OS sandbox. A model with unrestricted shell access can in principle do things hooks do not see. The full threat model, including what is not stopped, is in [docs/security-model.md](docs/security-model.md).
