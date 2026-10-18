# Startup Swarm (Claude Code plugin)

Give Claude Code a business or product problem. A hierarchy of specialised, isolated subagents runs a startup-style pipeline on it: evidence, product definition, design (architecture, threat model, compliance, cost), tested and audited code, and a release package. Hooks enforce who may read and write what, and three signed human gates (evidence, design/cost, release) stop the run from building on a bad premise.

> **Token-intensive by design.** A run dispatches many subagents for up to hours and re-reads the same artifacts many times. No benchmark has been run, so there is no cost figure yet; expect it to be one of the most expensive things you run in Claude Code. Defaults stop a run at 30 hours or 40M tokens (best-effort count). To spend less: use the default `lean` team, force a cheaper model for all subagents with `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`, and stop any time with `end`.

## Install

```
/plugin install swarm --marketplace AnimeshShaw/startup-swarm
```

## Use

```
/swarm:run   <your problem>        guided: a few questions up front, then three sign-offs
/swarm:god   <your problem>        god mode: asks you nothing, decides from its own research
/swarm:status                      stage, gates, spend, open questions
approve G1 | approve G2 | approve G3 | reject G2 <reason> | pause | resume | end
```

God mode output is an unvalidated hypothesis package plus code, not proof that anyone will pay. It never deploys, spends money or sends anything.

## What this plugin runs and touches (full disclosure)

- **Hooks** (`PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SubagentStop`) run `hooks/run.sh`, which starts the Python 3.9+ script `runtime/swarm.py` (standard library only, no network access, no telemetry). They can block tool calls, but **only while a swarm run is active** in the current project (`.venture/runtime/run.json` with `active: true`). In every other project they do nothing.
- **Files it writes** in the project where you start a run: `.venture/` (artifacts, plan, ledger, signed gate files), and whatever source and tests the engineer roles write.
- **Outside the project** it writes one signing key per run to `~/.swarm/keys/` so gate approvals cannot be forged by agents using file tools.
- **Network:** only through Claude Code's own `WebSearch`/`WebFetch` tools, used by the research roles, and through whatever test and build commands the engineer roles run in your project.
- **Shell:** engineer roles run tests and shell commands in your project folder with your user's permissions. Use a scratch folder or git worktree.
- **Secrets:** hooks block agents from reading or writing `.env` files and private keys. Never paste secrets into chat.
- **Known limits:** the shell guard is best-effort. Read `docs/security-model.md` in the repository before leaving a run unattended.

Source, documentation, tests and the security model: https://github.com/AnimeshShaw/startup-swarm

License: MIT.
