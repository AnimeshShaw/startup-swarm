# Settings and configuration

Everything you can change, where it lives, and what is *not* configurable. Defaults are starting values, not measured optima.

## Per-run options

Passed as leading words to `/swarm:run`, in any order.

| Option | Effect | Default |
|---|---|---|
| `god` | Never asks you anything; decides from research and logs each decision | `guided` |
| `full` | 17 specialist roles instead of 8 (more depth, roughly 2 to 3 times the cost) | `lean` |

```text
/swarm:run full god Design and build a GST-compliant invoicing app for freelancers
```

## Presets

| Preset | Roles | Use when |
|---|---|---|
| `lean` (default) | 8: strategy-head, source-verifier, product-head, architect, security-lead, engineer-senior, qa, auditor. Other roles are absorbed into these | First run, small problems, lower cost |
| `full` | 17, adding market-researcher, marketing-head, finance-legal, delivery-manager, devops, security-engineer, compliance-analyst, engineer-junior and red-team | You want specialist depth and accept the cost |

See [Roles](roles.md) for what each does.

## Budgets and limits

| Limit | Default |
|---|---|
| Wall clock | 1800 minutes (30 hours) |
| Tokens (best effort) | 40 million |
| Dispatches per stage | discover 40, define 20, design 40, plan 10, build 400, release 20 |
| Attempts per task and role | 3 |
| Re-plan after failures | 2 |
| Parallel subagents | 6 |
| Auto-continues per stage | 40 |
| CI timeout | 1800 seconds |

These live in `limits.json`. Token counting parses subagent transcripts and is best effort; if the host changes its format the count reads low. **Also set a spend limit on your Anthropic account.**

### Changing limits without forking

The plugin reads its configuration from its own `data/` folder, which is replaced on every update. To keep your values, copy that folder somewhere stable, edit `limits.json`, and point the plugin at it:

```bash
export SWARM_DATA=/path/to/my/swarm-data
```

Set it in your shell, or in the `env` block of your Claude Code settings. This path is exercised by the unit tests but has not been tried through Claude Code's settings file, so check `/swarm:status` after setting it.

## Choosing models

Each generated agent carries a model: `deep` roles (orchestrator, strategy, product, architect, security lead, auditor, red team) run on `opus`, `standard` roles on `sonnet`, `fast` roles on `haiku`.

Claude Code resolves a subagent's model in this order:

1. the per-call parameter
2. the agent's own `model` frontmatter
3. `CLAUDE_CODE_SUBAGENT_MODEL`
4. your session model

So setting only the environment variable does **not** override the plugin's per-role models. To force one model everywhere (Claude Code 2.1.257+):

```json
{
  "env": {
    "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet",
    "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"
  }
}
```

Put that in your user `settings.json`. To change the default tiers permanently, edit `core/config/models.json` in a fork and run `python build.py`.

!!! tip "Cost lever"
    Forcing a smaller model everywhere is the biggest cost reduction available, and also the biggest quality risk. Try `lean` on a small problem with each setting and compare the output before committing to long runs.

## API keys and `.env`

Your product will often need keys. The rules:

- Agents **never** see real secrets. Hooks block reading or writing `.env`, `.env.*` (except `.env.example`, `.env.sample`, `.env.template`, `.env.dist`), `*.pem`, and SSH private keys, including from shell commands.
- Roles write `.env.example` and ask for keys by variable name. **You create `.env` yourself and never paste values into chat.**
- Tests run on mocks by default. Live tests run through `swarm.py ci --task <id> --live -- <cmd>`, which loads `.env` into the test process only and masks values of 6+ characters in saved output.
- God mode never waits for keys. It builds on mocks and lists every missing key in the release report.
- The shell guard is best effort: a computed path such as `open(".e" + "nv")` is not caught. Keep `.env` in `.gitignore` and keep production credentials out of the folder.

## Files a run creates

Everything is inside `.venture/` in your project. Add it to `.gitignore`; the swarm does not.

| Path | Content |
|---|---|
| `brief.md`, `state/intake.md` | Your problem and intake answers |
| `artifacts/<type>/*.md` | Market brief, PRD, ADRs, threat model and the rest ([reference](artifacts.md)) |
| `work/<task>/` | Task spec, CI result, diff, audit |
| `questions/*.md` | Open and answered questions |
| `state/plan.json` | Stage and next step |
| `state/autopilot-decisions.md` | God-mode decision log |
| `gates/G*.json` | Signed gate decisions (runtime only) |
| `ledger.jsonl` | Append-only event log (runtime only) |

## Controlling a run

| Command | Effect |
|---|---|
| `/swarm:status` | Stage, gates, mode, spend, dispatch counts, open questions |
| `approve G1`, `approve G1 exploratory`, `approve G2`, `approve G3` | Record a gate. Type it as a normal message |
| `reject G2 <reason>` | Clear the gate; the reason goes to the rework |
| `/swarm:pause`, `/swarm:resume` | Stop or resume auto-continue |
| `/swarm:end` | Turn the run's hooks off and restore normal Claude Code behaviour |

## Hands-free runs

Claude Code, not the swarm, asks you to approve file edits and shell commands. A plugin cannot switch that off for you: plugin `settings.json` ignores `permissions`, and subagent `permissionMode` is ignored for plugin agents. Until you grant permission, a run stalls on approval dialogs ("apply this edit?"). Pick one:

| Option | How | Notes |
|---|---|---|
| Accept edits mode | Press **Shift+Tab** until the status line shows accept edits, or start with `claude --permission-mode acceptEdits` | Edits stop prompting; shell commands may still prompt |
| Project allow rules | Create `.claude/settings.local.json` in the run folder with the JSON below | Covers edits and shell commands; keep risky commands on `ask` |
| Headless | `claude -p "..." --permission-mode dontAsk --allowedTools "Edit" "Write" "Bash"` | Fails closed instead of waiting |

```json
{
  "permissions": {
    "allow": ["Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "PowerShell", "WebFetch", "WebSearch"],
    "ask": ["Bash(sudo *)", "Bash(git push *)", "Bash(npm publish *)", "Bash(docker push *)", "Bash(gh release *)", "Bash(ssh *)", "Bash(terraform apply *)", "Bash(kubectl apply *)"]
  }
}
```

The swarm's own hooks still apply on top: they deny out-of-scope writes, `.env` access and gate tampering, and a hook denial wins over an allow rule. Use a scratch folder, because allowing edits and shell commands removes the safety net of per-action approval. Do not use `bypassPermissions` outside a container or VM.

## What is not configurable

- The three gates cannot be skipped or approved by an agent. Only your typed message (or, in god mode only, the runtime's logged autopilot) passes one.
- God mode never deploys, spends money, or sends anything.
- Hooks only act while a run is active in the folder, so the plugin does nothing in your other projects.
