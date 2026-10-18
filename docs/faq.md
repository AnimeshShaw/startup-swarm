# FAQ

## Does it only work with Claude Code?

The enforced version does. Codex and Cursor get a reduced, sequential mode (one agent plays each role in turn, nothing is enforced), written from public docs and untested on a live host. Other tools are not supported. [Details](install.md).

## I added the marketplace but cannot find it in Discover

Adding a marketplace registers *your copy* of this catalog. Run `/plugin`, open the **Discover** tab, and look for the plugin named **swarm** (not "startup swarm"). If it is missing, run `/plugin marketplace update startup-swarm`. Listing in Anthropic's own directories is a separate submission and is at Anthropic's discretion.

## How much does a run cost?

Unknown. No benchmark has been run, and a full run launches many agents for hours. Set an account spend limit, start with `lean` on a small problem, and watch `/swarm:status` for the first hour. See [Settings](settings.md#budgets-and-limits).

## Is the output good enough to ship?

Treat it as a first draft from a well-read intern. Green tests and a clean PRD do not show that anyone will pay. Market numbers are desk research tagged `FACT`, `ESTIMATE` or `GUESS`; re-check the ones that matter.

## Can it prove demand?

No. It cannot interview customers, run ads or take payment. It produces the hypotheses and the real-world tests that would settle them; gate G1 is where you decide whether to run them.

## What does god mode change?

It never asks you anything and decides from its own research, logging every decision in `.venture/state/autopilot-decisions.md`. Gates are recorded as `by: autopilot`, G1 is always `exploratory`, and the release report must say so. It still never deploys, spends money or sends anything.

## Will it touch my other projects?

No. Hooks only act while `.venture/runtime/run.json` shows an active run in the current folder. Use a scratch folder or a git worktree anyway: a run writes source and runs tests and shell commands where you start it.

## Where do my API keys go?

In a `.env` you create yourself. Agents cannot read it. See [Settings](settings.md#api-keys-and-env).

## How do I report a bug or a security problem?

Bugs: [GitHub issues](https://github.com/AnimeshShaw/startup-swarm/issues). Security: use GitHub's private vulnerability reporting, see [SECURITY.md](https://github.com/AnimeshShaw/startup-swarm/blob/main/SECURITY.md).
