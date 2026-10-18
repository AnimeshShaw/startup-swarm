#!/bin/sh
# Finds a Python 3.9+ interpreter and runs the swarm runtime with the hook name and stdin passed through.
# If none is found it fails open (exit 0) and, on prompt hooks, tells the user that nothing is enforced.
here=$(dirname "$0")
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
    exec "$py" "$here/../runtime/swarm.py" "$@"
  fi
done
if [ "$1" = "prompt" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"[swarm] WARNING: Python 3.9+ was not found, so the swarm hooks are NOT enforcing anything. Install Python 3 and restart."}}'
fi
exit 0
