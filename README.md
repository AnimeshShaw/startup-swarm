<div align="center">

# 🐝 Startup Swarm

### An AI startup team for Claude Code

Give it a problem. A hierarchy of isolated specialist agents researches, defines, designs, builds, tests and audits it,<br>
and stops at **three human gates** so it can't sprint past a bad premise.

[![CI](https://github.com/AnimeshShaw/startup-swarm/actions/workflows/ci.yml/badge.svg)](https://github.com/AnimeshShaw/startup-swarm/actions/workflows/ci.yml)
[![Docs](https://github.com/AnimeshShaw/startup-swarm/actions/workflows/pages.yml/badge.svg)](https://animeshshaw.github.io/startup-swarm/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blueviolet.svg)](CHANGELOG.md)
[![Status](https://img.shields.io/badge/status-early%20(v0.1)-orange.svg)](docs/security-model.md#verification-status)
[![Token usage](https://img.shields.io/badge/token%20usage-high-red.svg)](#-cost-and-token-usage)

[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757.svg?logo=anthropic&logoColor=white)](https://code.claude.com/docs/en/discover-plugins)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)](core/runtime/swarm.py)
[![Hooks enforced](https://img.shields.io/badge/isolation-hook--enforced-blue.svg)](docs/security-model.md)
[![Human gates](https://img.shields.io/badge/human%20gates-3-purple.svg)](docs/architecture.md#pipeline-and-gates)
[![Codex](https://img.shields.io/badge/Codex-experimental-lightgrey.svg)](docs/install.md#codex)
[![Cursor](https://img.shields.io/badge/Cursor-experimental-lightgrey.svg)](docs/install.md#cursor)

[![Stars](https://img.shields.io/github/stars/AnimeshShaw/startup-swarm?style=flat&logo=github)](https://github.com/AnimeshShaw/startup-swarm/stargazers)
[![Forks](https://img.shields.io/github/forks/AnimeshShaw/startup-swarm?style=flat&logo=github)](https://github.com/AnimeshShaw/startup-swarm/network/members)
[![Issues](https://img.shields.io/github/issues/AnimeshShaw/startup-swarm)](https://github.com/AnimeshShaw/startup-swarm/issues)
[![Last commit](https://img.shields.io/github/last-commit/AnimeshShaw/startup-swarm)](https://github.com/AnimeshShaw/startup-swarm/commits/main)
[![Repo size](https://img.shields.io/github/repo-size/AnimeshShaw/startup-swarm)](https://github.com/AnimeshShaw/startup-swarm)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[**Documentation**](https://animeshshaw.github.io/startup-swarm/) ·
[**Install**](#-install) ·
[**Usage**](docs/usage.md) ·
[**Settings**](docs/settings.md) ·
[**Security model**](docs/security-model.md) ·
[**Changelog**](CHANGELOG.md)

</div>

---

```text
/swarm:run  Build a tool that lets small clinics in India reduce no-shows
```

That is the whole interface. The swarm interviews you once if the brief is vague, works for hours, and stops only at the three gates. Prefer no questions at all? `/swarm:god <problem>`.

> [!WARNING]
> **This is token-intensive on purpose.** A full run launches many agents, runs for hours and can use millions of tokens. There is no cost benchmark yet. Set an account spend limit, run it in a scratch folder, and start with a small problem. You choose the model; see [Settings](docs/settings.md#choosing-models).

> [!NOTE]
> **v0.1, early.** Unit and shell-level tests pass in CI on Linux and macOS. The hooks were probed on a live Claude Code session. Interactive runs, long runs, Windows, Codex and Cursor are **not** field-verified. [Exactly what is and isn't verified.](docs/security-model.md#verification-status)

## Contents

[Why](#-why) · [How it works](#-how-it-works) · [Features](#-features) · [Modes](#-pick-your-mode) · [Install](#-install) · [Cost](#-cost-and-token-usage) · [Compatibility](#-compatibility) · [Docs](#-documentation) · [Layout](#-repository-layout) · [Security](#-security) · [Contributing](#-contributing) · [License](#-license)

## 💡 Why

A single long prompt can write plausible code for a bad idea. Startups fail on the premise, not the syntax. Startup Swarm puts the checks a team would have in front of the code:

- **Evidence before design.** Every claim in the market brief is tagged `FACT`, `ESTIMATE` or `GUESS`. A separate verifier re-opens the cited sources. A red team argues against it before you see it.
- **Isolation that is enforced, not requested.** Roles can't read each other's notes, write outside their scope, edit locked tests or approve their own gates. Hooks deny it.
- **Tests before code, audit without bias.** QA locks tests by hash. Engineers run CI through a wrapper. The auditor sees only spec, tests, diff and CI result.
- **You decide at three points.** Evidence, design and cost, release. Signed with a key outside the project.

## ⚙️ How it works

```mermaid
flowchart LR
    A[Discover] --> G1{{G1 evidence}}
    G1 --> B[Define]
    B --> C[Design]
    C --> G2{{G2 design and cost}}
    G2 --> D[Plan]
    D --> E[Build]
    E --> F[Release]
    F --> G3{{G3 release}}
```

An **orchestrator** (a thin state machine) dispatches isolated **subagents** by role. All hand-offs are files under `.venture/`. A stdlib-only Python runtime, wired in through Claude Code hooks, enforces scopes, gates, test locks and budgets. See [Architecture](docs/architecture.md).

| Stage | Output |
|---|---|
| Discover | Cited market brief, evidence plan, source verification, red team |
| Define | PRD with testable acceptance criteria |
| Design | ADRs, threat model, compliance map, cost model, one-page decision pack |
| Plan | Sprints, tasks, dependency graph |
| Build | Locked tests, implementation, blind audit, security audit |
| Release | Deploy configuration (never executed), release report |

## ✨ Features

| | |
|---|---|
| 🧠 **18 roles, 2 presets** | `lean` (8 roles) by default, `full` (17) for depth |
| 🔒 **Hook-enforced guardrails** | File-scope guard, dispatch gate, test lock, artifact validator |
| 🚦 **Signed human gates** | Only a message you type passes G1, G2, G3 |
| ⚡ **One-shot** | `/swarm:run` asks at most 5 batched questions, then goes |
| 🤖 **God mode** | `/swarm:god` never asks; logs every decision; output labelled `EXPLORATORY` |
| 🔑 **Secrets policy** | Agents can't read `.env`; live tests inject keys into the test process only |
| 📒 **Append-only ledger** | Dispatches, denials, tamper events and gates are recorded |
| 🧪 **Tested runtime** | 65 tests, zero dependencies, Python 3.9 to 3.13 |

## 🎛 Pick your mode

| | `/swarm:run` (guided, default) | `/swarm:god` (god mode) |
|---|---|---|
| Asks you | up to 5 batched questions, 3 gate sign-offs | nothing |
| Decides | with your sign-off at G1, G2, G3 | everything, logged in `.venture/state/autopilot-decisions.md` |
| Output is | a package you approved at each gate | an **unvalidated hypothesis package** plus code, labelled `EXPLORATORY` and `AUTOPILOT` |
| Use when | you will act on the result | you want a fast first draft to react to |

God mode can't do customer discovery. Its "evidence" is desk research, so it ends at plausible, not proven. It never deploys, spends money or sends anything.

## 🚀 Install

**Claude Code** (full experience):

```bash
claude plugin marketplace add AnimeshShaw/startup-swarm
claude plugin install swarm@startup-swarm
```

or inside a session:

```text
/plugin marketplace add AnimeshShaw/startup-swarm
/plugin install swarm@startup-swarm
```

Then run it in a **scratch project folder**:

```text
/swarm:run Small physiotherapy clinics lose 20% of bookings to no-shows. Build a tool that fixes this.
```

Check it worked with `/swarm:status`. Try without installing: `claude --plugin-dir ./adapters/claude`.

Requires Python 3.9+ on PATH (`python3` or `python`). Per-host details, update and uninstall: [docs/install.md](docs/install.md).

## 💸 Cost and token usage

- A run is many agent sessions over hours. Defaults cap a run at 30 hours, 40 million tokens (best effort) and bounded dispatches per stage. [All limits](docs/settings.md#budgets-and-limits).
- `full` is estimated at 2 to 3 times the cost of `lean`. That is a guess; neither has been benchmarked.
- To force one cheaper model everywhere, set `CLAUDE_CODE_SUBAGENT_MODEL` and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`. [How model selection works.](docs/settings.md#choosing-models)
- Set a spend limit on your Anthropic account. The in-plugin counter is a guardrail, not a bill.

## 🧩 Compatibility

| Host | Experience | Status |
|---|---|---|
| **Claude Code** | Full: isolated subagents, enforcement hooks, one-shot commands | Hooks live-probed; interactive use in progress |
| Codex | Sequential, skills only, isolation by convention | Untested on a live host |
| Cursor | Sequential, skills only, isolation by convention | Untested on a live host |

Enforcement needs hooks that can veto a tool call and subagents that can't see each other's context. Claude Code provides both. Elsewhere, a single agent plays each role in turn and nothing stops it breaking the rules, so treat that output as weaker evidence.

## 📚 Documentation

Full site: **[animeshshaw.github.io/startup-swarm](https://animeshshaw.github.io/startup-swarm/)**

| Page | What's in it |
|---|---|
| [Install](docs/install.md) | Per host, update, uninstall, verify |
| [Usage guide](docs/usage.md) | Modes, commands, gates, good and bad fits, troubleshooting |
| [Settings](docs/settings.md) | Presets, budgets, models, `.env`, files a run creates |
| [Architecture](docs/architecture.md) | Pipeline, roles, how enforcement works |
| [Security model](docs/security-model.md) | What it stops, what it doesn't, verification status |
| [Roles](docs/roles.md) · [Artifacts](docs/artifacts.md) | Reference |
| [FAQ](docs/faq.md) | Quick answers |

## 🗂 Repository layout

```text
core/                  source of truth: roles, skills, protocol, config, runtime
adapters/_src/         per-host templates (hooks, commands, plugin manifest)
adapters/claude/       GENERATED Claude Code plugin
adapters/codex/        GENERATED Codex plugin (sequential)
adapters/cursor/       GENERATED Cursor plugin (sequential)
build.py               generates adapters, manifests and reference docs
tests/                 unit and shell-level tests
docs/                  documentation site source
.claude-plugin/        Claude Code marketplace manifest
```

Never edit generated folders by hand. Change `core/` or `adapters/_src/`, run `python build.py`, commit the result. CI fails if they drift.

## 🔐 Security

Plugins run with your user privileges, so read what you install. Hooks are policy enforcement, not an OS sandbox: a model with unrestricted shell access can in principle do things hooks don't see. Run in a scratch folder or worktree and keep secrets out of it. Threat model and known gaps: [docs/security-model.md](docs/security-model.md). Report vulnerabilities privately: [SECURITY.md](SECURITY.md).

## 🤝 Contributing

Issues and PRs are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).

```bash
git clone https://github.com/AnimeshShaw/startup-swarm && cd startup-swarm
python build.py && python -m unittest discover -s tests
```

## 📄 License

[MIT](LICENSE) © 2026 Animesh Shaw.

<sub>Output of this tool is a draft hypothesis package, not legal, financial or investment advice, and not a validated business case.</sub>
