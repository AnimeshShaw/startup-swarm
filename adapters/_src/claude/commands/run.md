---
description: "One-shot, TOKEN-INTENSIVE: give a problem, the swarm researches, designs, builds and audits it. Usage /swarm:run [god] [full] <problem>"
argument-hint: "[god] [full] <problem description>"
allowed-tools: Bash(python:*), Bash(python3:*), Read, Write
---
Run the swarm end to end on one problem. The user should not have to call any agent by hand.

Before initialising, show the user this notice (it is deliberately not hidden):

> **Heads up: this is token-intensive.** A run dispatches many subagents (research, design, tests, code, audits) for up to hours and re-reads the same artifacts many times. No benchmark has been run yet, so there is no cost figure, but expect it to be one of the most expensive things you run in Claude Code. Defaults stop a run at 30 hours or 40M tokens (best-effort count). To spend less: keep the default lean team, force one cheaper model for all subagents with `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` plus `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (Claude Code 2.1.257 or later), and type `end` to stop at any time.

Then continue; do not wait for confirmation.

1. Read the leading words of $ARGUMENTS. Accept, in any order and with or without a leading `--`: `god` (mode god), `guided` (mode guided, the default), `full` (preset full), `lean` (preset lean, the default). Everything after those words is the problem brief. If the brief is empty, ask the user for it in one line and stop.
2. Initialise the run, passing the brief on stdin so quotes cannot break the command:
```
python3 "${CLAUDE_PLUGIN_ROOT}/runtime/swarm.py" init --preset <preset> --mode <mode> --brief-file - <<'BRIEF'
<the brief, verbatim>
BRIEF
```
(If `python3` is not found, use `python`.) If it says a run is already active, tell the user and stop; do not use `--force` unless they ask to restart.
3. Invoke the `swarm:orchestrate` skill and follow it from the start: intake first (guided mode only), then stage `discover`. From now on you are the orchestrator: you dispatch the specialists yourself and do not do the work.
4. Hands-free: if Claude Code asks the user to approve file edits or commands during the run, that is its permission mode, not the swarm. Tell them once, in one line, to press Shift+Tab to accept edits or add the allow rules from `docs/settings.md#hands-free-runs` in the plugin repository. Never ask them to apply patches or run commands yourself.
5. Before you start, tell the user in two lines what will happen: the mode, and what they will be asked (guided: three sign-offs plus rare questions; god: nothing, and the output is unvalidated).
