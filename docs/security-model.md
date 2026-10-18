# Security model and verification status

Read this before leaving a run unattended. It is deliberately blunt.

## What the plugin is protecting against

The realistic failure modes of an autonomous multi-agent run, not a determined attacker:

1. An agent edits tests until they pass.
2. An agent or the orchestrator waves through a gate nobody approved.
3. A role reads another role's reasoning and inherits its mistakes (blind audit becomes rubber stamp).
4. Runaway loops and spend.
5. Fabricated sources and untagged claims.
6. Accidental destructive commands (`rm -rf .`, `git reset --hard` on locked tests).

## Mechanical vs. prompt-level

| Control | Kind | Strength |
|---|---|---|
| Path allow/deny per role for Read/Write/Edit/Grep/Glob | Hook (blocks the tool call) | Strong for built-in file tools |
| Gate files unwritable by agents; HMAC-style signature with key outside project | Hook + signature | Strong against agents using file tools; weak against a shell that can read the key (see below) |
| Test lock (SHA-256 of test files after QA; checked after every engineer) | Hook (detect + fail task) | Strong *detection*, even if a write slipped past the guard |
| CI result and diff written by runtime, not by the engineer | Runtime wrapper | Strong, if the engineer runs CI through the wrapper (the auditor refuses a task without `ci.json`) |
| Artifact schema, claim tags, PRD↔test-plan traceability | Hook (validate on write) | Strong for structure, **none for truth** |
| Attempt, dispatch, spawn, wall-clock caps | Hook | Strong |
| Token budget | SubagentStop parsing | Best-effort; depends on transcript format |
| Blind audit, red team, source verification | Prompt + file isolation | Reduces shared context only. Same model, same blind spots |
| Intake rules, god-mode decision logging, red-team rework limits, "never deploy or spend" | Prompt (orchestrator body) | Weak: nothing mechanical stops an orchestrator from ignoring them. God mode only *records* gates mechanically; it cannot prove the decisions were sound |

## Known bypasses and gaps

- **Bash is best-effort.** The guard parses redirections and common commands (`rm`, `mv`, `cp`, `tee`, `sed -i`, `git checkout|reset|...`), blocks protected paths and the runtime's control commands. It tracks `cd` and is case-insensitive (Windows and macOS file systems are), but it does not understand `node -e`, `curl -o`, variable indirection such as `S=swarm; python $S.py`, encoded paths, or anything else dynamic. Literal references to protected paths inside `python -c` strings are caught; computed ones are not. The test-lock hash is the backstop for tests; nothing equivalent backstops source files outside the role's scope.
- **The signing key is readable by any process running as you.** A subagent with Bash could read `~/.swarm/keys/<run id>` and forge a gate if it located it and wrote the gate file with a non-file-tool method. The bash guard blocks the obvious paths; it is not a sandbox. If this matters, run in a container or VM.
- **God mode is a decision to remove the human check.** The autopilot gate verifies artifacts exist, validate, have no open blocking questions, and the log has a section. It does not verify the content is correct.
- **Subagent identity** relies on `agent_type` in the hook payload (confirmed in Claude Code's hook docs) with a file-based fallback. If a host omits it, the fallback applies the rules of every currently running role at once (the strictest combination). That is safe but over-blocking: the orchestrator may be refused writes while subagents run.
- **Fail-open hooks.** A crashing or missing hook does not block. Crashes are logged as `hook_error`; a missing Python is not detectable from inside the plugin.
- **Correlated errors.** One model family plays every role. Disagreement between roles is weaker evidence than disagreement between humans or between model families.
- **Strategy layer produces hypotheses, not evidence.** No amount of schema checking turns desk research into customer validation.
- **Agents can run code.** Engineers execute tests and arbitrary shell in your folder with your user's permissions and network. That is the product working as intended, not a bug. Isolate accordingly.
- **Secrets.** `.env` and key files are blocked for file tools and literal shell references; computed paths are not caught, and a human pasting a key into chat puts it in the transcript.
- **Prompt injection.** Roles read web pages. A hostile page can try to steer a role. File-scope limits bound the damage to what that role could write anyway; they do not stop it from writing a bad artifact. The verifier and red team are the mitigation, not a guarantee.

## Verification status

| Area | Status | How |
|---|---|---|
| Runtime logic (guard, dispatch, gates, validation, ledger, autopilot, CI wrapper) | **Verified** | 65 tests: unit tests (`tests/test_runtime.py`) and a shell-level simulation of whole runs (`tests/test_e2e.py`) |
| Configuration consistency (roles, presets, absorbers, schemas, skills, partition of test files) | **Verified** | Config tests |
| Hook command lines in a real shell with simulated payloads | **Verified** | Scripted sandbox run, see below |
| Claude Code hook payload fields (`agent_type`, `cwd`), plugin load, hook firing, role resolution for the main thread and a dispatched subagent, gate-file write denial, artifact validation, Stop-hook auto-continue | **Verified on a live session** (Claude Code 2.1.302, headless, one short probe) | Ledger from the probe |
| Slash commands (`/swarm:run`, `/swarm:god`) end to end, intake questions, approvals typed by a human | **Not verified live** | Needs an interactive session |
| Subagent tool name (`Agent` vs `Task`) | Both matched in hooks | Docs say `Agent` |
| A full multi-hour run end to end with real model calls | **Not done** | |
| Codex plugin and Cursor plugin load and behave | **Not verified** | Written from public docs |
| Cost per run, duration, quality of output | **Unknown** | No benchmark |

## First live checks to run (15 minutes)

1. Install, `/swarm:status` responds.
2. `/swarm:run` on a toy problem. Confirm `.venture/runtime/run.json` exists and the status line appears on your next message.
3. Ask Claude to write `.venture/gates/G1.json`. Expect a denial and a `deny` event in `ledger.jsonl`.
4. After the first subagent returns, check `ledger.jsonl` has `dispatch` entries with the right roles. If roles show as `orchestrator` for subagent writes, role resolution is falling back; report it.
5. `approve G1` with no artifacts: expect "cannot approve G1 yet".
