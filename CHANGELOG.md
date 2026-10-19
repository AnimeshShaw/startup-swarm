# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-10-19

### Fixed
- **CI wrapper blocked on every marketplace install.** The Bash guard rejected any command containing `.claude/`, and the plugin lives under `~/.claude/`, so engineers could not run `swarm.py ci` and handed back patches instead. Only the exact runtime path is now exempt; other `.claude/` access stays protected.
- Typing `resume` now reactivates a run ended with `end` (human-typed message only).

### Changed
- Agent contract rule 10 and orchestrator rules: agents never ask the human to apply patches or run commands; only batched decisions (max 4 per message).
- Docs: new "Hands-free runs" section explaining that edit and command approval prompts come from Claude Code's permission mode, with the settings that remove them.

## [0.1.0] - 2026-10-18

### Added
- Hierarchical agent swarm for Claude Code: orchestrator, heads and workers in isolated subagent contexts, in `lean` (8 roles) and `full` (17 roles) presets.
- Hook-enforced runtime (`swarm.py`, Python standard library only): file-scope guard, dispatch gate, post-write artifact validation, test lock, signed human gates, Stop-hook auto-continue, token ledger.
- Three human gates (evidence, design and cost, release) and a guided one-shot `/swarm:run`.
- `/swarm:god` autopilot mode that decides from desk research, logs every decision, and labels its output `EXPLORATORY` and `AUTOPILOT`.
- Secrets policy: `.env` and key files blocked for the agent; `ci --live` injects `.env` into the test process only and masks values in output.
- Reduced sequential adapters for Codex and Cursor (skills only, no hooks).
- Marketplace manifests for Claude Code, Codex and Cursor.
- 65 tests (unit and shell-level simulation).

### Known limits
- Interactive slash commands, a full multi-hour run, Windows, Codex and Cursor are not verified on live hosts.
- No cost or quality benchmark yet. Runs are token-intensive.
