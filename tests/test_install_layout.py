"""The plugin must work from where it is really installed, not from a repo checkout.

Marketplace installs live under ~/.claude/plugins/..., a path the guard treats as protected for agents.
These tests copy the built plugin into such layouts and drive it through the real hook entry point."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
subprocess.run([sys.executable, str(ROOT / "build.py")], check=True, capture_output=True)
BUILT = ROOT / "adapters" / "claude"


def hook(plugin, name, payload):
    r = subprocess.run(["sh", str(plugin / "hooks" / "run.sh"), name], input=json.dumps(payload),
                       capture_output=True, text=True, cwd=payload.get("cwd"))
    return r.returncode, r.stdout, r.stderr


class InstallLayout(unittest.TestCase):
    LAYOUTS = [
        (".claude", "plugins", "cache", "startup-swarm", "swarm", "0.1.1"),
        ("Program Files", ".claude", "plugins", "cache", "swarm"),   # space in the path
        ("u", ".claude", ".swarm-x", "plugin"),                      # looks protected twice over
    ]

    def install(self, parts):
        base = pathlib.Path(tempfile.mkdtemp(prefix="swarm-layout-"))
        plugin = base.joinpath(*parts)
        shutil.copytree(BUILT, plugin)
        proj = base / "project"
        proj.mkdir()
        r = subprocess.run([sys.executable, str(plugin / "runtime" / "swarm.py"), "init", "--brief-text", "x"],
                           capture_output=True, text=True, cwd=proj)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)   # includes the init self-test
        return plugin, proj

    def guard(self, plugin, proj, role, cmd):
        return hook(plugin, "guard", {"cwd": str(proj), "tool_name": "Bash", "tool_input": {"command": cmd}, "agent_type": "swarm:" + role})

    def test_ci_wrapper_runs_from_every_layout(self):
        for parts in self.LAYOUTS:
            plugin, proj = self.install(parts)
            rt = plugin / "runtime" / "swarm.py"
            for role in ("engineer-senior", "engineer-junior"):
                for cmd in ('python "%s" ci --task T1 -- python -c pass' % rt,
                            "python3 '%s' diff --task T1" % rt):
                    code, out, err = self.guard(plugin, proj, role, cmd)
                    self.assertNotIn("deny", out, "%s %s -> %s" % (parts, role, out))

    def test_other_dot_claude_access_stays_protected(self):
        plugin, proj = self.install(self.LAYOUTS[0])
        rt = plugin / "runtime" / "swarm.py"
        for cmd in ("cat ~/.claude/settings.json",
                    'python "%s" ci --task T1 -- cat .claude/settings.json' % rt,
                    'python "%s" ci --task T1 -- true; echo x > .claude/hooks/swarm.py' % rt,
                    "echo x >> %s" % rt,
                    'python "%s" init --force' % rt):
            code, out, err = self.guard(plugin, proj, "engineer-senior", cmd)
            self.assertIn("deny", out, cmd)


if __name__ == "__main__":
    unittest.main()
