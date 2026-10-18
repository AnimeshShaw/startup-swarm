---
description: Show swarm run status and metrics
allowed-tools: Bash(python:*), Bash(python3:*)
---
Run status and metrics for the active swarm run:

!`python3 "${CLAUDE_PLUGIN_ROOT}/runtime/swarm.py" status 2>/dev/null || python "${CLAUDE_PLUGIN_ROOT}/runtime/swarm.py" status`

Summarise in five lines: stage, gates, what is running or blocked, spend so far, and what the human needs to do next, if anything.
