"""End-to-end simulation: the real hook command lines from hooks.json, run through a real shell,
fed hook-shaped JSON payloads, driving a whole god-mode run (and a guided run up to a human gate).
No model is involved: 'subagents' are simulated by writing the files each role would write.
Live Claude Code behaviour is NOT covered here."""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.test_runtime import make_artifact  # noqa: E402  (also rebuilds adapters)

PLUGIN = ROOT / "adapters" / "claude"
HOOKS = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
BASH = shutil.which("bash")


class Sim(unittest.TestCase):
    mode = "god"

    @classmethod
    def setUpClass(cls):
        if not BASH:
            raise unittest.SkipTest("bash not available")

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="sim-home-")
        self.proj = pathlib.Path(tempfile.mkdtemp(prefix="sim-proj-")).resolve()
        self.env = dict(os.environ, HOME=self.home, CLAUDE_PLUGIN_ROOT=str(PLUGIN))
        subprocess.run(["git", "init", "-q"], cwd=self.proj, check=False)
        r = self.cli("init", "--preset", "lean", "--mode", self.mode, "--brief-file", "-", inp="Build a tiny CLI that adds numbers.")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.v = self.proj / ".venture"

    def cli(self, *args, inp=""):
        return subprocess.run([sys.executable, str(PLUGIN / "runtime" / "swarm.py"), *args], input=inp, text=True, capture_output=True, cwd=self.proj, env=self.env)

    def fire(self, event, tool=None, tool_input=None, agent=None, prompt=None):
        """Run every matching hook command; return (denied, stdout, stderr)."""
        payload = {"cwd": str(self.proj), "hook_event_name": event, "tool_name": tool, "tool_input": tool_input or {}}
        if agent:
            payload["agent_type"] = "swarm:" + agent
        if prompt is not None:
            payload["prompt"] = prompt
        denied, out, err = False, "", ""
        for entry in HOOKS.get(event, []):
            m = entry.get("matcher")
            if m and not re.fullmatch(m, tool or ""):
                continue
            for h in entry["hooks"]:
                r = subprocess.run([BASH, "-c", h["command"]], input=json.dumps(payload), text=True, capture_output=True, cwd=self.proj, env=self.env)
                out += r.stdout
                err += r.stderr
                if r.returncode == 2 or '"permissionDecision": "deny"' in r.stdout or '"decision": "block"' in r.stdout:
                    denied = True
        return denied, out, err

    def write(self, role, rel, text):
        """A role tries to write a file through the Write tool: guard, then the file, then post-write."""
        p = self.proj / rel
        d, out, err = self.fire("PreToolUse", "Write", {"file_path": str(p), "content": text}, agent=role)
        if d:
            return d, out + err
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        d, out, err = self.fire("PostToolUse", "Write", {"file_path": str(p), "content": text}, agent=role)
        return d, out + err

    def art(self, role, typ, name="a", **front):
        d, msg = self.write(role, ".venture/artifacts/%s/%s.md" % (typ, name), make_artifact(typ, **front))
        self.assertFalse(d, "%s writing %s: %s" % (role, typ, msg))

    def run_role(self, role, task, stage, **kw):
        prompt = "TASK: %s\nSTAGE: %s\nINPUTS: x\nOUTPUT: y" % (task, stage)
        ti = {"subagent_type": "swarm:" + role, "prompt": prompt}
        d, out, err = self.fire("PreToolUse", "Agent", ti)
        return d, out + err, ti

    def dispatch_ok(self, role, task, stage):
        d, msg, ti = self.run_role(role, task, stage)
        self.assertFalse(d, "dispatch %s refused: %s" % (role, msg))
        return ti

    def finish(self, ti):
        return self.fire("PostToolUse", "Agent", ti)

    def set_plan(self, **kw):
        plan = json.loads((self.v / "state" / "plan.json").read_text())
        plan.update(kw)
        d, msg = self.write("orchestrator", ".venture/state/plan.json", json.dumps(plan))
        self.assertFalse(d, msg)

    def decisions(self, g):
        p = self.v / "state" / "autopilot-decisions.md"
        old = p.read_text() if p.exists() else ""
        d, msg = self.write("orchestrator", ".venture/state/autopilot-decisions.md", old + "\n## %s\n- assumption chosen, confidence medium, GUESS\n" % g)
        self.assertFalse(d, msg)

    def stop(self):
        return self.fire("Stop")


class TestGodRunEndToEnd(Sim):
    mode = "god"

    def test_full_run(self):
        # --- discover
        d, _, _ = self.run_role("product-head", "x", "define")
        self.assertTrue(d, "define must be locked before G1")
        ti = self.dispatch_ok("strategy-head", "d1", "discover")
        self.art("strategy-head", "market-brief")
        self.art("strategy-head", "evidence-plan")
        self.finish(ti)
        ti = self.dispatch_ok("source-verifier", "d2", "discover")
        self.art("source-verifier", "verification")
        self.finish(ti)
        ti = self.dispatch_ok("auditor", "d3", "discover")
        self.art("auditor", "redteam", gate="G1")
        self.finish(ti)
        # attacks along the way
        self.assertTrue(self.write("orchestrator", ".venture/gates/G1.json", "{}")[0])
        self.assertTrue(self.write("strategy-head", "src/app.py", "x")[0])
        self.decisions("G1")
        self.set_plan(waiting="G1")
        d, out, _ = self.stop()
        self.assertIn("Autopilot recorded G1", out)
        self.assertEqual(json.loads((self.v / "gates" / "G1.json").read_text())["by"], "autopilot")
        # --- define + design
        ti = self.dispatch_ok("product-head", "p1", "define")
        self.art("product-head", "prd")
        self.finish(ti)
        self.set_plan(stage="design")
        for role, typ in (("architect", "adr"), ("security-lead", "threat-model"), ("security-lead", "compliance-map"), ("architect", "cost-model")):
            ti = self.dispatch_ok(role, "g-" + typ, "design")
            self.art(role, typ)
            self.finish(ti)
        ti = self.dispatch_ok("product-head", "p2", "design")
        self.art("product-head", "decision-pack")
        self.finish(ti)
        ti = self.dispatch_ok("auditor", "p3", "design")
        self.art("auditor", "redteam", name="g2", gate="G2")
        self.finish(ti)
        self.decisions("G2")
        self.set_plan(waiting="G2")
        self.assertIn("Autopilot recorded G2", self.stop()[1])
        # --- plan + build
        ti = self.dispatch_ok("architect", "pl1", "plan")
        self.art("architect", "backlog")
        self.finish(ti)
        d, _, _ = self.run_role("engineer-senior", "T1", "build")
        self.assertTrue(d, "engineers need QA's locked tests first")
        ti = self.dispatch_ok("qa", "T1-qa", "build")
        d, msg = self.write("qa", "tests/test_app.py", "import unittest\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(1 + 1, 2)\n")
        self.assertFalse(d, msg)
        self.art("qa", "test-plan")
        self.assertFalse(self.finish(ti)[0])
        self.assertTrue((self.v / "runtime" / "tests.lock.json").exists())
        ti = self.dispatch_ok("engineer-senior", "T1", "build")
        self.assertFalse(self.write("engineer-senior", "src/app.py", "def add(a, b):\n    return a + b\n")[0])
        self.assertTrue(self.write("engineer-senior", "tests/test_app.py", "import unittest\n")[0], "engineer must not touch tests")
        b = self.fire("PreToolUse", "Bash", {"command": "echo hi > tests/test_app.py"}, agent="engineer-senior")
        self.assertTrue(b[0])
        r = self.cli("ci", "--task", "T1", "--", sys.executable, "-m", "unittest", "discover", "-s", "tests")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads((self.v / "work" / "T1" / "ci.json").read_text())["passed"])
        self.assertFalse(self.finish(ti)[0])
        ti = self.dispatch_ok("auditor", "T1-aud", "build")
        self.art("auditor", "audit", name="T1")
        self.finish(ti)
        ti = self.dispatch_ok("security-lead", "T1-sec", "build")
        self.art("security-lead", "audit", name="T1-sec")
        self.finish(ti)
        # tampering after the lock is caught
        ti = self.dispatch_ok("engineer-senior", "T2", "build")
        (self.proj / "tests" / "test_app.py").write_text("import unittest\n")
        self.assertTrue(self.finish(ti)[0])
        # --- release
        self.set_plan(stage="release")
        ti = self.dispatch_ok("architect", "r1", "release")
        d, msg = self.write("architect", ".venture/artifacts/release-report/a.md", make_artifact("release-report") + "\nEXPLORATORY AUTOPILOT: no human reviewed any gate.\n")
        self.assertFalse(d, msg)
        self.finish(ti)
        ti = self.dispatch_ok("auditor", "r2", "release")
        self.art("auditor", "redteam", name="g3", gate="G3")
        self.finish(ti)
        self.decisions("G3")
        self.set_plan(waiting="G3")
        self.assertIn("Autopilot recorded G3", self.stop()[1])
        self.set_plan(stage="done", waiting=None)
        self.assertEqual(self.stop()[1], "")
        st = self.cli("status").stdout
        self.assertIn("mode=god", st)
        summary = json.loads(st[st.index("{"):])
        self.assertEqual(summary["autopilot_gates"], 3)
        self.assertEqual(summary["tamper_events"], 1)
        self.assertGreater(summary["guard_denies"], 3)
        v = self.cli("validate")
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)


class TestGuidedHumanGate(Sim):
    mode = "guided"

    def test_human_gate_flow(self):
        for role, typ in (("strategy-head", "market-brief"), ("strategy-head", "evidence-plan"), ("source-verifier", "verification")):
            self.art(role, typ)
        d, out, _ = self.fire("UserPromptSubmit", prompt="approve G1")
        self.assertTrue(d)
        self.assertIn("cannot approve G1", out)
        self.art("auditor", "redteam", gate="G1")
        self.set_plan(waiting="G1")
        self.assertEqual(self.stop()[1], "")
        self.assertTrue(self.fire("Stop")[0] is False)
        d, out, _ = self.fire("UserPromptSubmit", prompt="approve G1")
        self.assertIn("recorded approved for G1", out)
        self.assertEqual(json.loads((self.v / "gates" / "G1.json").read_text())["by"], "human")
        d, out, _ = self.fire("UserPromptSubmit", prompt="what is going on")
        self.assertIn("mode=guided", out)
        self.assertFalse(self.run_role("product-head", "p1", "define")[0])

    def test_autopilot_cannot_be_used_in_guided_runs(self):
        r = self.cli("autopilot", "G1")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.v / "gates" / "G1.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
