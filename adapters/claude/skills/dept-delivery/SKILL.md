---
name: dept-delivery
description: "Delivery playbook: backlog, sprints, task files, dependency graph, parallel safety. Use when planning build work."
---

# Delivery playbook

- Tasks are small: one engineer, a few hours of work, one concern.
- `task.md` fields: goal; acceptance ids served; files it may touch; files it must not touch; test command; `complexity: low|high`; depends on.
- Parallel only if the file sets are disjoint and no task consumes another's output. Build the dependency graph first; sprint 1 is the thinnest vertical slice that runs end to end.
- Order by risk: the task that could invalidate the architecture goes first.
- Sprint = a set of independent tasks plus the QA pass before them and the audit pass after them. Keep sprint size within the preset's spawn caps.
- Every task has an owner role and an exit check (CI green, audit approve, security not veto).
