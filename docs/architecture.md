# Architecture

## Shape

One **orchestrator** (the main Claude Code thread) is a thin state machine. It never researches, writes artifacts or code. It dispatches **isolated subagents** by role. Subagents cannot spawn subagents, so a role that wants specialists replies with `SPAWN:` lines and the orchestrator dispatches them. All hand-offs are files under `.venture/`; no role sees another's conversation.

```
human ── gates G1 G2 G3 ──┐
                          ▼
                    orchestrator ──► strategy ─► product ─► architect/security/finance ─► delivery
                          │             │            │                │                       │
                          │       source-verifier    │            red team                 QA ─► engineers ─► auditor
                          ▼
                 hooks: guard · dispatch gate · after-task · post-write · stop · approval
```

## Pipeline and gates

`discover → G1 → define → design → G2 → plan → build → release → G3 → done`

| Gate | Question it answers | Needs (all final, valid) |
|---|---|---|
| G1 | Is the premise worth building on? | market-brief, evidence-plan, verification, redteam(G1) |
| G2 | Is the design, scope and cost acceptable? | prd, adr, threat-model, compliance-map, cost-model, decision-pack, redteam(G2) |
| G3 | Is the release package acceptable? | release-report, redteam(G3) |

Gate files are signed with a per-run key stored under `~/.swarm/keys/`, outside the project. A gate recorded by a human (typed message) or, in god mode only, by the runtime's autopilot (`by: autopilot`) verifies; anything else does not.

## Presets

`lean`: 8 roles. The rest are *absorbed*: the dispatch hook tells the orchestrator which role plus skill to use instead (for example marketing work goes to `strategy-head` with `swarm:dept-marketing`). `full`: 17 roles. Role table: [roles.md](roles.md).

## Enforcement (hooks)

| Hook | Does |
|---|---|
| `PreToolUse` guard | Per-role ordered allow/deny lists for read, write, web and bash targets. Hard-denies gates, ledger, runtime, `.git`, `.claude`, CI results and diffs for everyone |
| `PreToolUse` Task/Agent (dispatch) | Requires `TASK:`/`STAGE:` headers; checks stage, gate prerequisites, required artifacts, spawn caps, attempt cap, stage budgets, wall and token budgets, preset absorption |
| `PostToolUse` Task/Agent | QA locks SHA-256 of the test files and checks that PRD acceptance criteria are traced to the test plan; after engineers/devops, verifies nothing locked changed |
| `PostToolUse` Write/Edit | Validates artifacts against the schema and feeds errors back |
| `UserPromptSubmit` | Parses `approve`/`reject`/`pause`/`resume`/`end`, writes signed gate files, injects the status line |
| `Stop` | Auto-continues the orchestrator unless waiting; in god mode runs the autopilot gate |
| `SubagentStop` | Token accounting |

Role resolution uses `agent_type` from the hook payload, falling back to `.venture/runtime/active.json`; the main thread is `orchestrator`. The guard is inert unless `.venture/runtime/run.json` has `active: true`.

## Design choices, briefly

- **Files, not chat, between roles.** Cuts hand-off drift and makes every step auditable.
- **Mechanical checks over persuasion.** Test lock by hash, CI via a runtime wrapper that writes the authoritative result, diffs produced by the runtime, schema validation on every write.
- **Independence is partly cosmetic on one model.** A blind auditor, a source verifier and a red team reduce shared context, not shared training. Where a claim can be checked by a test, a fetch or a human, the pipeline makes it do so.
- **The human decides at three points** because those are the three places a wrong turn is expensive and a model cannot know.

## Layout of this repository

```
core/            source of truth: agents/, skills/, config/, protocol/, runtime/swarm.py
build.py         generates adapters/ and docs/roles.md, docs/artifacts.md from core/
adapters/claude  Claude Code plugin (generated)
adapters/codex   Codex plugin (generated, sequential)
adapters/cursor  Cursor plugin (generated, sequential)
adapters/_src/   hand-written parts the generator copies (hooks, commands, manifest)
tests/           unit tests for the runtime and for config consistency
```
Edit `core/` or `adapters/_src/`, run `python build.py`, run the tests, commit both.
