# Install

The repository is a multi-host marketplace. Each host reads its own manifest at the repo root and installs the matching generated plugin from `adapters/`.

| Host | Manifest at repo root | Plugin dir | Experience |
|---|---|---|---|
| Claude Code | `.claude-plugin/marketplace.json` | `adapters/claude` | **Full**: isolated subagents, enforcement hooks, one-shot commands |
| Codex | `.agents/plugins/marketplace.json` | `adapters/codex` | **Sequential**: skills only, isolation by convention |
| Cursor | `.cursor-plugin/marketplace.json` | `adapters/cursor` | **Sequential**: skills only, isolation by convention |

Why the difference: enforcement needs hooks that can veto a tool call and subagents that cannot see each other's context. Claude Code provides both in a form this plugin uses. The other two hosts get the same roles, skills and runtime, but a single agent plays each role in turn, so nothing stops it breaking the rules. Treat their output as weaker evidence. Codex and Cursor support was written from their public docs and has **not been tested on a live host**.

## Requirements

- Python 3.9 or newer reachable as `python3` or `python`. Standard library only.
- Git (for engineers' commits and for installing from GitHub).
- If Python is missing, Claude Code hooks fail open (a missing hook does not block). The plugin would then enforce nothing. Check with `/swarm:status` after install.

## Claude Code

```
claude plugin marketplace add AnimeshShaw/startup-swarm
claude plugin install swarm@startup-swarm
```
or in one command (Claude Code 2.1.292+), or from inside a session (2.1.275+):
```
claude plugin install swarm --marketplace AnimeshShaw/startup-swarm
/plugin install swarm --marketplace AnimeshShaw/startup-swarm
```
Restart or reload plugins if the commands do not appear. Then try:
```
/swarm:status
```
which should say `no active swarm run here`.

Try it from a local checkout without installing:
```
claude --plugin-dir ./adapters/claude
```
Update: `claude plugin update swarm@startup-swarm`. Remove: `claude plugin uninstall swarm@startup-swarm`.

**Run it in a throwaway project folder.** Hooks only activate when `.venture/runtime/run.json` exists with `active: true`, so the plugin does nothing in your other projects, but a run creates `.venture/`, writes source and runs tests in the folder where you start it.

## Codex

```
codex plugin marketplace add AnimeshShaw/startup-swarm
```
then enable the `swarm` plugin from the Plugins directory. Pin a ref with `--ref`. Ask Codex to use the `swarm-run` skill with your problem. Codex hook support for plugins is limited to manually installed plugins and the format differs from Claude's, so no hooks are shipped.

## Cursor

Cursor plugins are distributed as git repositories through marketplaces. Import this repo into a team marketplace (Customize → marketplace → add from GitHub), or for local testing copy `adapters/cursor` to `~/.cursor/plugins/local/swarm` and reload the window. Then ask the agent to use the `swarm-run` skill.

## Any other agent that reads Agent Skills

Copy `adapters/codex/skills/*` into the host's skills directory and `adapters/codex/{roles,runtime,data}` next to it. The `swarm-run` skill says where it expects them.

## Verify the install worked (Claude Code)

1. `/swarm:status` responds.
2. Start a run in a scratch folder: `/swarm:run build a todo CLI`.
3. In that run, `/swarm:status` shows `mode=guided stage=discover`.
4. While the run is active, ask Claude to create the file `.venture/gates/G1.json`. It must be refused. This is the cheapest proof the hooks are live.

If step 4 succeeds, hooks are not loading: see "Troubleshooting" in [usage.md](usage.md).
