# Usage guide

## 1. The one-shot path (what most people want)

```
/swarm:run <your problem, in as much or as little detail as you have>
```

Examples:
```
/swarm:run Small physiotherapy clinics in Pune lose about 20% of bookings to no-shows. Build a tool that fixes this.
/swarm:run god Build a CLI that turns a folder of meeting notes into a weekly status report
/swarm:run full Design and build a GST-compliant invoicing app for freelancers
```

Leading words, in any order (a leading `--` is accepted):

| Word | Effect | Default |
|---|---|---|
| `god` | God mode: never asks you anything | `guided` |
| `full` | 17 specialist roles instead of 8 (more depth, roughly 2 to 3x the cost) | `lean` |

What happens next, in guided mode:

1. **Intake** (once, only if needed). If the brief leaves out something that changes the whole run (customer, market, constraints, regulated data), the swarm asks at most 5 questions in a single batch, each with a recommended default. Accept the defaults with one click or answer. A specific brief gets no questions.
2. **Discover.** Strategy builds a market brief and an evidence plan. A separate verifier checks the brief's cited sources. A red team attacks it.
3. **Gate G1.** You are shown the 3 riskiest hypotheses and the real-world tests that would settle them. Reply `approve G1` once you have evidence, or `approve G1 exploratory` to continue without it (everything downstream is labelled EXPLORATORY).
4. **Define and design.** PRD, architecture decision records, threat model, compliance map, cost model, then a one-page decision pack, then red team.
5. **Gate G2.** Reply `approve G2`, or `reject G2 <reason>` and the swarm reworks.
6. **Plan and build.** A backlog is cut into sprints. For each sprint: QA writes tests first and they are locked by hash; engineers implement in parallel and run CI through the runtime wrapper; a blind auditor reviews spec + tests + diff + CI result; security audits. Merge only on green CI, an `approve` audit and no security veto.
7. **Release and gate G3.** Deploy configuration (never executed), final security audit, release report, red team. Reply `approve G3`.

You can walk away between gates. When a gate is reached the swarm stops and tells you exactly what to type.

## 2. God mode

```
/swarm:god <problem>
```
equivalent to `/swarm:run god <problem>`.

- Never uses the question tool and never waits on you. Open questions are answered by the orchestrator with a logged rationale.
- Each gate is recorded by the runtime as `by: autopilot` once the same prerequisites a human gate needs are met (artifacts valid, no open blocking questions) **and** the decision log has a `## G1` / `## G2` / `## G3` section. G1 is always `exploratory`.
- Red team blockers get up to 2 rework rounds; after that they are recorded as accepted risk and the run continues.
- A task that exhausts its retry cap is de-scoped and logged, not escalated.
- The release report must say EXPLORATORY and AUTOPILOT and that no human reviewed a gate. The runtime refuses to record G3 otherwise.
- Hard limits that god mode does not lift: nothing is deployed, nothing is bought, nothing is emailed or posted. Token and wall-clock budgets still apply.
- You can still interrupt: `pause`, `resume`, `end`, or even `approve G1` yourself (recorded as human).

**Read the output as a first draft from a very well-read intern, not as a verdict.** Everything in the market brief is desk research. The evidence plan will be drafted but not executed. A plausible market, a clean PRD and green tests do not show that anyone will pay.

## 3. Commands

| Command | What it does |
|---|---|
| `/swarm:run [god] [full] <problem>` | Start a one-shot run |
| `/swarm:god [full] <problem>` | Start a god-mode run |
| `/swarm:status` | Stage, gates, mode, spend, dispatch counts, open questions |
| `approve G1` / `approve G1 exploratory` / `approve G2` / `approve G3` | Record a gate. Type it as a normal message; `/swarm:approve G1` also works |
| `reject G2 <reason>` | Clears the gate; the reason is passed to the rework |
| `pause` / `resume` | Stop auto-continue / resume from the saved plan |
| `end` | Turn the run's hooks off and restore normal Claude Code behaviour |

Gates can only be passed by a message *you* type; the orchestrator and every subagent are blocked from writing gate files and the files are signed with a key outside the project.

## 4. Manual control (advanced)

You do not need this for normal use. The runtime has a CLI (`runtime/swarm.py`, path shown in every status line):

```
python swarm.py init --preset lean --mode guided --brief-file brief.md
python swarm.py status
python swarm.py validate          # check every artifact against its schema
python swarm.py diff --task T3    # write the authoritative diff.patch
python swarm.py ci --task T3 -- pytest -q
```
`init` flags: `--preset lean|full`, `--mode guided|god`, `--brief-text`, `--brief-file` (`-` reads stdin), `--dir`, `--force` (restart), `--sequential` (hosts without hooks).

## 5. What to use it for

Good fits:
- A software product or tool whose scope you can describe and whose value you will test with real people afterwards. The pipeline produces the hypotheses, the PRD, a design you can argue with, and tested code.
- Turning a vague idea into a falsifiable plan: what must be true, what to test first, what it costs.
- Greenfield projects. Test-first and blind audit work best on code the swarm itself writes.
- A second opinion on an existing plan: put your doc in the brief and read the red team output.

Poor fits, do not use it for:
- **Proving demand.** It cannot interview customers, run ads, or take payment. Treat its market numbers as estimates to check.
- **Regulated or safety-critical software** (medical devices, payments handling, anything with legal sign-off) beyond a first draft. The compliance map is a checklist generator, not legal advice.
- **Large existing codebases.** Isolation and test locking assume the swarm owns the tests. It will work, but expect friction and noisy diffs.
- **Anything you cannot afford to leave running unattended**: it spends tokens, writes files and runs tests and shell commands in the folder. Use a scratch folder or a git worktree.
- **Hosts other than Claude Code**, if you need the guarantees. There isolation is a convention.
- **Secrets.** Do not put credentials in the brief or the project folder; agents can read the project.

## 6. Cost, time, and budgets

These are limits, not forecasts. No benchmark run has been done, so any cost or duration number would be a guess.

| Limit | Default | Where |
|---|---|---|
| Wall clock | 1800 minutes (30 h) | `core/config/limits.json` → `run.wall_minutes` |
| Tokens (best-effort) | 40 million | `run.tokens` |
| Dispatches per stage | discover 40, define 20, design 40, plan 10, build 400, release 20 | `stage_budgets` |
| Attempts per task and role | 3 | `max_attempts_per_task_role` |
| Parallel subagents | 6 | `max_parallel_total` |
| Auto-continues per stage | 40 | `max_auto_continues_per_stage` |

Token counting parses subagent transcripts and is best-effort; if the host changes its format the count reads low. Set a spend limit on your account too.

**Choosing the model.** The generated agents carry a model each (`deep` roles on `opus`, `standard` on `sonnet`, `fast` on `haiku`). Claude Code resolves a subagent's model in this order: per-call parameter, the agent's own `model` frontmatter, `CLAUDE_CODE_SUBAGENT_MODEL`, then your session model, so the environment variable alone does not override the plugin's per-role models. To force one model everywhere, set both `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` and `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (Claude Code 2.1.257+, e.g. in the `env` block of your settings).

Model tiers: `deep` roles (orchestrator, strategy, product, architect, security lead, auditor, red team) run on `opus`, `standard` on `sonnet`, `fast` on `haiku`. Edit `core/config/models.json`, rebuild with `python build.py`.

## 6b. API keys and `.env`

Your product will often need keys (an LLM provider, a payment API). The rules:

- Agents never see real secrets. Hooks block agents from reading or writing `.env`, `.env.*` (except `.env.example`, `.env.sample`, `.env.template`), `*.pem` and SSH private keys, including from shell commands.
- Roles write `.env.example` (names, purpose, where to get each) and raise a `kind: secret` question with variable names only. The orchestrator relays them to you; **you create `.env` yourself and never paste values into chat**.
- Tests run on mocks or recorded fixtures by default, so a run costs no product-API money unless you opt in. Live tests run through `swarm.py ci --task <id> --live -- <cmd>`, which loads `.env` into the test process only and masks the values in the saved output.
- God mode never waits for keys. It builds on mocks and lists every missing key in the release report. Create `.env` before you start if you want live tests.
- Limits: the shell guard is best-effort (a computed path such as `open(".e"+"nv")` is not caught), and directory-wide Grep skips gitignored files only by ripgrep's defaults. Keep `.env` in `.gitignore` and keep production credentials out of the folder.

## 7. Files a run creates

All inside `.venture/` in your project (add it to `.gitignore`; the swarm does not).

| Path | Content | Who writes |
|---|---|---|
| `brief.md` | Your problem (+ intake answers in `state/intake.md`) | init / orchestrator |
| `artifacts/<type>/*.md` | Market brief, PRD, ADRs, threat model, ... ([reference](artifacts.md)) | roles |
| `work/<task>/` | Task spec, CI result, diff, audit | delivery, runtime, auditor |
| `questions/*.md` | Open and answered questions | roles / orchestrator |
| `state/plan.json` | Stage, next step, waiting | orchestrator |
| `state/autopilot-decisions.md` | God mode decision log | orchestrator |
| `gates/G*.json` | Signed gate decisions | runtime only |
| `ledger.jsonl` | Append-only event log (dispatches, denials, tamper events, gates) | runtime only |
| `runtime/` | Counters, locks, test hashes | runtime only |

## 8. Claim tags

Every factual statement in a strategy artifact carries one of: `[FACT src=<url or file:line>]`, `[ESTIMATE basis=<how derived>]`, `[GUESS]`. The validator enforces tags and a minimum count; the source verifier re-fetches cited sources and writes a `verified_pct`. G1 requires 80% or sends the brief back (max 2 loops). The tags show provenance, not truth: a verifier running on the same model can share the author's blind spots, and a live URL does not prove a claim.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `/swarm:*` commands missing | Plugin not installed or not reloaded | `/plugin`, reinstall, restart Claude Code |
| Nothing is ever blocked | Hooks not firing or Python not found | Run `python3 --version`; in the run folder `ls .venture/runtime/run.json`; read `.venture/ledger.jsonl` for `hook_error` |
| "needs gate Gx" when dispatching | Gate not passed | Guided: type `approve Gx`. God: ensure the `## Gx` section exists in the decisions log and end the turn |
| `cannot approve G1 yet:` | Missing or invalid final artifacts, or an open blocking question | The message lists each problem |
| `X may not write Y` | Role isolation working as designed | The role should write a question instead |
| Run stops after a while | A budget, a cap, or pause | `/swarm:status`; `ledger.jsonl` has `continue_cap`; `resume` |
| `a run is already active here` | Previous run in this folder | `end`, or init with `--force` to restart (wipes counters, not artifacts) |
| Tamper event in ledger | Test files changed after QA locked them | The task is failed and sent back; this is expected behaviour |
| Windows: hooks silent | No `sh`/Git Bash or no Python on PATH | Install Git for Windows and Python 3, reopen the terminal |

## 10. Safe-use checklist

1. Scratch folder or worktree, committed clean.
2. No secrets in the folder or brief.
3. Account spend limit set.
4. First run: `lean`, a small problem, guided, and watch `/swarm:status` for the first hour.
5. Check `ledger.jsonl` for `deny` and `tamper` counts. Zero denies on a long run is suspicious, not reassuring.
