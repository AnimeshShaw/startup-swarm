# Contributing

Thanks for helping. This project is small on purpose: one stdlib-only Python runtime, plain-Markdown agent definitions, and a build script that generates the per-host adapters.

## Ground rules

- `core/` and `adapters/_src/` are the source of truth. **Never edit** `adapters/claude`, `adapters/codex`, `adapters/cursor`, the root `*/marketplace.json` files or `docs/roles.md` / `docs/artifacts.md` by hand; run `python build.py` and commit the output. CI fails if generated files drift.
- The runtime must stay dependency-free and work on Python 3.9+.
- Any change to enforcement (guard, gates, secrets) needs a test that fails without the change.
- Do not add network calls, telemetry or code that reads outside the project directory.

## Workflow

```bash
git clone https://github.com/AnimeshShaw/startup-swarm
cd startup-swarm
python build.py                      # regenerate adapters
python -m unittest discover -s tests -v
claude plugin validate adapters/claude --strict   # if you have Claude Code
```

1. Open an issue for anything non-trivial before writing code.
2. Branch from `main`, keep PRs focused, add tests, update `CHANGELOG.md`.
3. Use clear imperative commit messages (`Fix guard bypass via cd`).

## Reporting security issues

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## Changing the guard

Anything in `check`, `check_bash` or the hooks must keep `tests/test_install_layout.py` green. It installs the plugin the way users get it (under `~/.claude/plugins/...`), not from a checkout, because a guard that works from the repo can still block the plugin's own CI wrapper once installed.
