---
name: dept-devops
description: Infrastructure playbook: hosting choice, CI, environments, secrets, deploy, rollback, observability. Use for infra work.
---
# Infrastructure playbook

- Hosting: compare 2 or 3 options on monthly cost at low and high load, operational burden, lock-in and region or compliance fit. Pick the one a solo operator can run.
- CI: lint, tests, dependency audit, secret scan on every push; build once, deploy the same artifact.
- Environments: local, staging, production; production changes only through the pipeline.
- Secrets in the platform's secret store; rotate on a stated schedule; never in the repository or images.
- Deploy: automated, with a one-command rollback tried at least once before release.
- Observability: structured logs, error tracking, an uptime check, and one alert that reaches a human.
- Backups: what is backed up, how often, and a restore actually tested.
