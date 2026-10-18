---
description: "God mode, TOKEN-INTENSIVE: never asks you anything, decides from its own research. Usage /swarm:god [full] <problem>"
argument-hint: "[full] <problem description>"
allowed-tools: Bash(python:*), Bash(python3:*), Read, Write
---
Before initialising, show the user this notice (it is deliberately not hidden):

> **Heads up: this is token-intensive.** A run dispatches many subagents (research, design, tests, code, audits) for up to hours and re-reads the same artifacts many times. No benchmark has been run yet, so there is no cost figure, but expect it to be one of the most expensive things you run in Claude Code. Defaults stop a run at 30 hours or 40M tokens (best-effort count). To spend less: keep the default lean team, force one cheaper model for all subagents with `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` plus `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (Claude Code 2.1.257 or later), and type `end` to stop at any time.

Then continue; do not wait for confirmation.

This is /swarm:run in god mode. Treat $ARGUMENTS as if it began with the word `god`, then follow exactly the steps of the `/swarm:run` command: initialise with `--mode god`, invoke the `swarm:orchestrate` skill, and run to the end without asking the user anything.

Tell the user in two lines before you start: no human gate will be asked, every decision is logged in `.venture/state/autopilot-decisions.md`, and the result is an unvalidated hypothesis package plus built code, not proof that the idea works. Nothing is deployed, bought or sent.

Initialise with (use `python` if `python3` is not found):
```
python3 "${CLAUDE_PLUGIN_ROOT}/runtime/swarm.py" init --preset <lean, or full if the first word is full> --mode god --brief-file - <<'BRIEF'
<the brief, verbatim>
BRIEF
```
