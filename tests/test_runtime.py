import contextlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
subprocess.run([sys.executable, str(ROOT / "build.py")], check=True, capture_output=True)
HOME = tempfile.mkdtemp(prefix="swarm-home-")
os.environ["HOME"] = HOME
spec = importlib.util.spec_from_file_location("swarm", ROOT / "adapters" / "claude" / "runtime" / "swarm.py")
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


def hook(fn, inp):
    out, err, code = io.StringIO(), io.StringIO(), 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            fn(inp)
        except SystemExit as e:
            code = e.code or 0
    return code, out.getvalue(), err.getvalue()


def is_denied(res):
    return '"permissionDecision": "deny"' in res[1]


def make_artifact(typ, status="final", **front):
    S = sw.cfg("schemas")[typ]
    fm = {"type": typ, "version": "1", "author": "test", "status": status}
    for k in S.get("extra_front", []):
        fm[k] = (S.get("enums", {}).get(k) or ["x"])[0] if k != "verified_pct" else "95"
    fm.update(front)
    head = "---\n" + "\n".join("%s: %s" % kv for kv in fm.items()) + "\n---\n"
    per = max(60, (S.get("min_words", 0) // max(1, len(S["headings"]))) + 10)
    body = ""
    for h in S["headings"]:
        body += "\n## %s\n%s\n" % (h, " ".join(["word"] * per))
    if S.get("claims"):
        body += "\n" + " ".join("claim [FACT src=https://example.com/%d] " % i for i in range(S.get("min_claims", 1) + 1)) + "\n"
    body += "\nAC-1 AC-2 AC-3 T-1 T-2 T-3 TASK-1 costs $100 per month\n"
    return head + body


class Base(unittest.TestCase):
    preset = "lean"

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="swarm-proj-")).resolve()
        self._cwd = os.getcwd()
        os.chdir(self.tmp)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sw.cmd_init(["--preset", self.preset, "--dir", str(self.tmp), "--brief-text", "test brief"])
        self.v = self.tmp / ".venture"

    def tearDown(self):
        os.chdir(self._cwd)

    def put(self, rel, text):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def art(self, typ, name="a", **kw):
        return self.put(".venture/artifacts/%s/%s.md" % (typ, name), make_artifact(typ, **kw))

    def approve_gate(self, g, status="approved"):
        at = sw.iso()
        sw.save_json(self.v / "gates" / (g + ".json"), {"gate": g, "status": status, "by": "human", "at": at, "sig": sw.sign(self.v, g, status, at)})

    def guard(self, role, tool, **ti):
        return hook(sw.cmd_guard, {"cwd": str(self.tmp), "agent_type": "swarm:" + role if role else None, "tool_name": tool, "tool_input": ti})

    def dispatch(self, role, task="t1", stage="discover", **extra):
        prompt = "TASK: %s\nSTAGE: %s\nINPUTS: x" % (task, stage)
        return hook(sw.cmd_dispatch, {"cwd": str(self.tmp), "tool_input": dict({"subagent_type": role, "prompt": prompt}, **extra)})

    def finish(self, role, task="t1", stage="discover"):
        return hook(sw.cmd_after_task, {"cwd": str(self.tmp), "tool_input": {"subagent_type": role, "prompt": "TASK: %s\nSTAGE: %s" % (task, stage)}})

    def prompt(self, text):
        return hook(sw.cmd_prompt, {"cwd": str(self.tmp), "prompt": text})


class TestGuard(Base):
    def test_engineer_write_rules(self):
        self.assertFalse(is_denied(self.guard("engineer-senior", "Write", file_path=str(self.tmp / "src/app.py"))))
        self.assertTrue(is_denied(self.guard("engineer-senior", "Write", file_path=str(self.tmp / "tests/test_a.py"))))
        self.assertTrue(is_denied(self.guard("engineer-senior", "Edit", file_path="src/a.test.js")))
        self.assertTrue(is_denied(self.guard("engineer-senior", "Write", file_path=".venture/artifacts/prd/x.md")))
        self.assertFalse(is_denied(self.guard("engineer-senior", "Write", file_path=".venture/work/T1/result.md")))
        self.assertTrue(is_denied(self.guard("engineer-senior", "Write", file_path=".venture/work/T1/ci.json")))
        self.assertTrue(is_denied(self.guard("engineer-senior", "Write", file_path="../outside.txt")))

    def test_qa_and_orchestrator(self):
        self.assertFalse(is_denied(self.guard("qa", "Write", file_path="tests/test_a.py")))
        self.assertTrue(is_denied(self.guard("qa", "Write", file_path="src/app.py")))
        self.assertTrue(is_denied(self.guard(None, "Write", file_path="src/app.py")))
        self.assertFalse(is_denied(self.guard(None, "Write", file_path=".venture/state/plan.json")))
        self.assertTrue(is_denied(self.guard(None, "Bash", command="ls")))

    def test_gates_unwritable_by_anyone(self):
        for r in (None, "engineer-senior", "architect", "product-head"):
            self.assertTrue(is_denied(self.guard(r, "Write", file_path=".venture/gates/G1.json")), r)
            self.assertTrue(is_denied(self.guard(r, "Write", file_path=".venture/runtime/run.json")), r)

    def test_auditor_is_blind(self):
        self.assertTrue(is_denied(self.guard("auditor", "Read", file_path=".venture/work/T1/result.md")))
        self.assertFalse(is_denied(self.guard("auditor", "Read", file_path=".venture/work/T1/diff.patch")))
        self.assertTrue(is_denied(self.guard("auditor", "Grep", path=".", pattern="x")))
        self.assertTrue(is_denied(self.guard("auditor", "Glob", path=".venture", pattern="**/*")))
        self.assertFalse(is_denied(self.guard("auditor", "Grep", path="src", pattern="x")))
        self.assertTrue(is_denied(self.guard("auditor", "Bash", command="cat x")))

    def test_verifier_cannot_see_research_notes(self):
        self.assertTrue(is_denied(self.guard("source-verifier", "Read", file_path=".venture/work/research/1.md")))
        self.assertFalse(is_denied(self.guard("source-verifier", "Read", file_path=".venture/artifacts/market-brief/a.md")))

    def test_unknown_role_cannot_write(self):
        self.assertTrue(is_denied(self.guard("general-purpose", "Write", file_path="src/a.py")))
        self.assertFalse(is_denied(self.guard("general-purpose", "Read", file_path="src/a.py")))

    def test_inactive_run_is_not_restricted(self):
        run = sw.load_json(self.v / "runtime" / "run.json")
        run["active"] = False
        sw.save_json(self.v / "runtime" / "run.json", run)
        self.assertEqual(self.guard(None, "Write", file_path="src/a.py")[1], "")


class TestBash(Base):
    def b(self, role, cmd):
        return is_denied(self.guard(role, "Bash", command=cmd))

    def test_engineer_bash(self):
        self.assertTrue(self.b("engineer-senior", "echo x > tests/a.py"))
        self.assertTrue(self.b("engineer-senior", "rm -rf tests"))
        self.assertTrue(self.b("engineer-senior", "rm -rf ."))
        self.assertTrue(self.b("engineer-senior", "rm -rf *"))
        self.assertTrue(self.b("engineer-senior", "git checkout -- tests/test_a.py"))
        self.assertTrue(self.b("engineer-senior", "sed -i s/a/b/ tests/test_a.py"))
        self.assertFalse(self.b("engineer-senior", "pytest tests/ > out.txt"))
        self.assertFalse(self.b("engineer-senior", "npm test 2>&1 | tail -20"))
        self.assertFalse(self.b("engineer-senior", "echo ok > src/new.py"))

    def test_runtime_and_protected_paths(self):
        self.assertTrue(self.b("engineer-senior", "python /x/runtime/swarm.py init --force"))
        self.assertTrue(self.b("engineer-senior", "python swarm.py approve G1"))
        self.assertTrue(self.b("engineer-senior", "cat .venture/ledger.jsonl"))
        self.assertTrue(self.b("engineer-senior", "cat .venture/gates/G1.json"))
        self.assertFalse(self.b("engineer-senior", 'python "/x/runtime/swarm.py" ci --task T1 -- pytest -q'))
        self.assertTrue(self.b("engineer-senior", 'python "/x/runtime/swarm.py" ci --task T1 -- rm tests/a.py'))

    def test_cd_is_tracked_and_keys_protected(self):
        self.assertTrue(self.b("engineer-senior", "cd .venture && echo {} > gates/G1.json"))
        self.assertTrue(self.b("engineer-senior", "cd tests; rm test_a.py"))
        self.assertFalse(self.b("engineer-senior", "cd src && echo ok > a.py"))
        self.assertTrue(self.b("engineer-senior", "cat ~/.swarm/keys/abc"))

    def test_paths_are_case_insensitive(self):
        g = str(self.tmp / ".VENTURE" / "Gates" / "G1.json")
        self.assertTrue(is_denied(self.guard("engineer-senior", "Write", file_path=g, content="{}")))
        self.assertTrue(is_denied(self.guard("orchestrator", "Write", file_path=g, content="{}")))
        self.assertTrue(is_denied(self.guard("engineer-senior", "Write", file_path=str(self.tmp / "TESTS" / "test_x.py"), content="")))
        self.assertTrue(self.b("engineer-senior", "echo x > .Venture/Gates/G1.json"))

    def test_read_outside_project_denied(self):
        self.assertTrue(is_denied(self.guard("engineer-senior", "Read", file_path=os.path.expanduser("~/.swarm/keys/x"))))

    def test_qa_cannot_touch_source(self):
        self.assertTrue(self.b("qa", "echo x > src/app.py"))
        self.assertFalse(self.b("qa", "echo x > tests/test_a.py"))


class TestDispatch(Base):
    def test_gate_order(self):
        r = self.dispatch("product-head", stage="define")
        self.assertTrue(is_denied(r))
        self.assertIn("G1", r[1])
        self.assertFalse(is_denied(self.dispatch("strategy-head")))

    def test_header_required(self):
        r = hook(sw.cmd_dispatch, {"cwd": str(self.tmp), "tool_input": {"subagent_type": "strategy-head", "prompt": "do it"}})
        self.assertTrue(is_denied(r))

    def test_non_swarm_and_absorbed_roles(self):
        self.assertTrue(is_denied(self.dispatch("general-purpose")))
        r = self.dispatch("marketing-head", stage="define")
        self.assertIn("strategy-head", r[1])
        self.assertIn("dept-marketing", r[1])

    def test_wrong_stage_for_role(self):
        self.assertTrue(is_denied(self.dispatch("qa", stage="discover")))

    def test_spawn_cap_and_attempts(self):
        self.assertFalse(is_denied(self.dispatch("strategy-head", task="t1")))
        self.assertTrue(is_denied(self.dispatch("strategy-head", task="t2")))
        self.finish("strategy-head", "t1")
        self.assertFalse(is_denied(self.dispatch("strategy-head", task="t1")))
        self.finish("strategy-head", "t1")
        self.assertFalse(is_denied(self.dispatch("strategy-head", task="t1")))
        self.finish("strategy-head", "t1")
        r = self.dispatch("strategy-head", task="t1")
        self.assertTrue(is_denied(r))
        self.assertIn("attempts", r[1])

    def test_full_preset_accepts_specialists(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            sw.cmd_init(["--preset", "full", "--dir", str(self.tmp), "--force"])
        self.assertFalse(is_denied(self.dispatch("market-researcher", task="r1")))
        self.assertFalse(is_denied(self.dispatch("market-researcher", task="r2")))


class TestGates(Base):
    def g1_artifacts(self):
        for t in ("market-brief", "evidence-plan", "verification"):
            self.art(t)
        self.art("redteam", gate="G1")

    def test_approve_blocked_without_artifacts(self):
        code, out, _ = self.prompt("approve G1")
        self.assertIn('"decision": "block"', out)
        self.assertFalse(sw.gate_ok(self.v, "G1"))

    def test_approve_after_artifacts_and_unlocks_define(self):
        self.g1_artifacts()
        code, out, _ = self.prompt("/swarm:approve G1")
        self.assertIn("recorded approved for G1", out)
        self.assertTrue(sw.gate_ok(self.v, "G1"))
        self.assertFalse(is_denied(self.dispatch("product-head", stage="define")))

    def test_forged_gate_file_rejected(self):
        sw.save_json(self.v / "gates" / "G1.json", {"gate": "G1", "status": "approved", "by": "human", "at": "now", "sig": "nope"})
        self.assertFalse(sw.gate_ok(self.v, "G1"))
        self.assertTrue(is_denied(self.dispatch("product-head", stage="define")))

    def test_exploratory_only_for_g1(self):
        self.assertIn("recorded exploratory", self.prompt("approve G1 exploratory")[1])
        self.assertTrue(sw.gate_ok(self.v, "G1"))
        self.assertIn('"decision": "block"', self.prompt("approve G2 exploratory")[1])

    def test_blocking_question_prevents_approval(self):
        self.g1_artifacts()
        self.put(".venture/questions/x-1.md", "---\nrole: x\nblocking: true\nstatus: open\n---\nWhich market?")
        self.assertIn("blocking question", self.prompt("approve G1")[1])
        self.assertIn("blocking question", self.prompt("approve G1 exploratory")[1])

    def test_reject_clears_gate(self):
        self.approve_gate("G2")
        self.prompt("reject G2 cost too high")
        self.assertFalse(sw.gate_ok(self.v, "G2"))
        self.assertIn("cost too high", (self.v / "state" / "feedback-G2.md").read_text())

    def test_design_needs_final_prd(self):
        self.approve_gate("G1")
        self.assertTrue(is_denied(self.dispatch("architect", stage="design")))
        self.art("prd")
        self.assertFalse(is_denied(self.dispatch("architect", stage="design")))

    def test_pause_resume_end(self):
        self.prompt("pause")
        self.assertEqual(sw.plan_state(self.v)["waiting"], "user paused")
        self.prompt("resume")
        self.assertIsNone(sw.plan_state(self.v)["waiting"])
        self.prompt("end")
        self.assertIsNone(sw.find_vdir(str(self.tmp)))


class TestValidation(Base):
    def errs(self, typ, text):
        p = self.put("x.md", text)
        return sw.validate_artifact(p, typ)

    def test_good_artifacts_pass(self):
        for t in sw.cfg("schemas"):
            if t.startswith("_"):
                continue
            self.assertEqual(self.errs(t, make_artifact(t)), [], t)

    def test_claim_rules(self):
        good = make_artifact("market-brief")
        self.assertTrue(any("no src" in e for e in self.errs("market-brief", good + "\n[FACT] unsourced")))
        self.assertTrue(any("no basis" in e for e in self.errs("market-brief", good + "\n[ESTIMATE] x")))
        self.assertTrue(any("tagged claims" in e for e in self.errs("market-brief", good.replace("[FACT", "[F"))))

    def test_structure_rules(self):
        self.assertTrue(any("missing section" in e for e in self.errs("prd", make_artifact("prd").replace("## Non-goals", "## Other"))))
        self.assertTrue(any("too short" in e for e in self.errs("prd", "---\ntype: prd\nversion: 1\nauthor: a\nstatus: final\n---\n## Problem\nx")))
        self.assertTrue(any("one of" in e for e in self.errs("audit", make_artifact("audit", verdict="maybe"))))

    def test_post_write_hook(self):
        p = self.put(".venture/artifacts/prd/bad.md", "---\ntype: prd\nversion: 1\nauthor: a\nstatus: final\n---\n## Problem\nx")
        code, _, err = hook(sw.cmd_post_write, {"cwd": str(self.tmp), "tool_input": {"file_path": str(p)}})
        self.assertEqual(code, 2)
        self.assertIn("failed validation", err)
        p = self.put(".venture/artifacts/prd/draft.md", "---\ntype: prd\nversion: 1\nauthor: a\nstatus: draft\n---\n## Problem\nx")
        self.assertEqual(hook(sw.cmd_post_write, {"cwd": str(self.tmp), "tool_input": {"file_path": str(p)}})[0], 0)


class TestBuildFlow(Base):
    def prep_build(self):
        self.approve_gate("G1")
        self.approve_gate("G2")
        self.art("prd")
        self.art("backlog")

    def test_test_lock_and_tamper(self):
        self.prep_build()
        self.put("tests/test_a.py", "def test_a(): assert True\n")
        self.assertFalse(is_denied(self.dispatch("qa", stage="build")))
        code, _, err = self.finish("qa", stage="build")
        self.assertEqual(code, 2)
        self.assertIn("AC-", err)
        self.art("test-plan")
        self.assertFalse(is_denied(self.dispatch("qa", task="t2", stage="build")))
        self.assertEqual(self.finish("qa", "t2", "build")[0], 0)
        self.assertTrue((self.v / "runtime" / "tests.lock.json").exists())
        self.assertFalse(is_denied(self.dispatch("engineer-senior", task="e1", stage="build")))
        self.assertEqual(self.finish("engineer-senior", "e1", "build")[0], 0)
        self.assertFalse(is_denied(self.dispatch("engineer-senior", task="e2", stage="build")))
        (self.tmp / "tests" / "test_a.py").write_text("def test_a(): pass\n")
        code, _, err = self.finish("engineer-senior", "e2", "build")
        self.assertEqual(code, 2)
        self.assertIn("changed after QA locked", err)
        self.assertEqual(sw.summarize(self.v)["tamper_events"], 1)

    def test_engineers_blocked_without_lock(self):
        self.prep_build()
        self.assertTrue(is_denied(self.dispatch("engineer-senior", stage="build")))

    def test_ci_wrapper(self):
        self.prep_build()
        self.put("tests/test_a.py", "x\n")
        sw.save_json(self.v / "runtime" / "tests.lock.json", {"hash": sw.tests_state(self.v)[0]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                sw.cmd_ci(["--task", "T1", "--", sys.executable, "-c", "print(42)"])
        self.assertEqual(cm.exception.code, 0)
        rec = sw.load_json(self.v / "work" / "T1" / "ci.json")
        self.assertTrue(rec["passed"] and rec["tests_intact"])
        (self.tmp / "tests" / "test_a.py").write_text("changed\n")
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                sw.cmd_ci(["--task", "T1", "--", sys.executable, "-c", "print(1)"])
        self.assertNotEqual(cm.exception.code, 0)
        self.assertFalse(sw.load_json(self.v / "work" / "T1" / "ci.json")["passed"])


class TestAutonomy(Base):
    def stop(self):
        return hook(sw.cmd_stop, {"cwd": str(self.tmp)})

    def test_stop_continues_until_waiting(self):
        self.assertIn('"decision": "block"', self.stop()[1])
        plan = sw.plan_state(self.v)
        plan["waiting"] = "G1"
        sw.save_json(self.v / "state" / "plan.json", plan)
        self.assertEqual(self.stop()[1], "")

    def test_continue_cap(self):
        n = sw.cfg("limits")["max_auto_continues_per_stage"]
        for _ in range(n):
            self.assertIn("block", self.stop()[1])
        self.assertEqual(self.stop()[1], "")

    def test_status_summary_counts(self):
        self.dispatch("strategy-head")
        self.prompt("hello")
        s = sw.summarize(self.v)
        self.assertEqual(s["dispatches_total"], 1)
        self.assertEqual(s["human_prompts"], 1)


class TestGodMode(Base):
    def setUp(self):
        super().setUp()
        with contextlib.redirect_stdout(io.StringIO()):
            sw.cmd_init(["--preset", "lean", "--mode", "god", "--dir", str(self.tmp), "--brief-text", "b", "--force"])

    def stop(self):
        return hook(sw.cmd_stop, {"cwd": str(self.tmp)})

    def wait_for(self, g):
        plan = sw.plan_state(self.v)
        plan["waiting"] = g
        sw.save_json(self.v / "state" / "plan.json", plan)

    def g1_ready(self, log=True):
        for t in ("market-brief", "evidence-plan", "verification"):
            self.art(t)
        self.art("redteam", gate="G1")
        if log:
            self.put(".venture/state/autopilot-decisions.md", "## G1\n- chose X because Y (confidence: medium, GUESS)\n")

    def test_mode_recorded_and_visible(self):
        self.assertEqual(sw.run_state(self.v)["mode"], "god")
        self.assertIn("mode=god", sw.status_line(self.v))
        self.assertEqual(sw.summarize(self.v)["mode"], "god")

    def test_autopilot_records_g1_as_exploratory_and_unlocks_next_stage(self):
        self.g1_ready()
        self.wait_for("G1")
        out = self.stop()[1]
        self.assertIn("Autopilot recorded G1", out)
        self.assertEqual(sw.gate_status(self.v, "G1"), "exploratory")
        self.assertEqual(sw.gate_by(self.v, "G1"), "autopilot")
        self.assertIsNone(sw.plan_state(self.v)["waiting"])
        self.assertFalse(is_denied(self.dispatch("product-head", stage="define")))
        self.assertEqual(sw.summarize(self.v)["autopilot_gates"], 1)

    def test_autopilot_refuses_without_decision_log_or_artifacts(self):
        self.g1_ready(log=False)
        self.wait_for("G1")
        out = self.stop()[1]
        self.assertIn("autopilot-decisions.md", out)
        self.assertFalse(sw.gate_ok(self.v, "G1"))
        self.assertEqual(sw.plan_state(self.v)["waiting"], "G1")
        self.assertTrue(sw.autopilot_gate(self.v, "G2"))

    def test_open_blocking_question_blocks_autopilot(self):
        self.g1_ready()
        self.put(".venture/questions/x-1.md", "---\nrole: x\nblocking: true\nstatus: open\n---\nQ?")
        self.wait_for("G1")
        self.assertIn("blocking question", self.stop()[1])
        self.assertFalse(sw.gate_ok(self.v, "G1"))

    def test_god_never_waits_for_a_question(self):
        self.wait_for("need human input about pricing")
        out = self.stop()[1]
        self.assertIn("never waits", out)
        self.assertIsNone(sw.plan_state(self.v)["waiting"])

    def test_human_pause_is_respected(self):
        self.prompt("pause")
        self.assertEqual(self.stop()[1], "")

    def test_dispatch_denial_points_at_autopilot(self):
        r = self.dispatch("product-head", stage="define")
        self.assertTrue(is_denied(r))
        self.assertIn("autopilot", r[1])

    def test_autopilot_gate_is_worthless_outside_god_mode(self):
        self.g1_ready()
        self.assertEqual(sw.autopilot_gate(self.v, "G1"), [])
        run = sw.run_state(self.v)
        run["mode"] = "guided"
        sw.save_json(self.v / "runtime" / "run.json", run)
        self.assertIsNone(sw.gate_status(self.v, "G1"))
        self.assertTrue(is_denied(self.dispatch("product-head", stage="define")))
        self.assertTrue(sw.autopilot_gate(self.v, "G1"))

    def test_forged_autopilot_file_rejected(self):
        sw.save_json(self.v / "gates" / "G1.json", {"gate": "G1", "status": "approved", "by": "autopilot", "at": "t", "sig": "nope"})
        self.assertFalse(sw.gate_ok(self.v, "G1"))
        at = sw.iso()
        sw.save_json(self.v / "gates" / "G1.json", {"gate": "G1", "status": "approved", "by": "autopilot", "at": at, "sig": sw.sign(self.v, "G1", "approved", at, "human")})
        self.assertFalse(sw.gate_ok(self.v, "G1"))

    def test_agents_cannot_write_gate_files(self):
        for role in ("orchestrator", "engineer-senior", "strategy-head"):
            self.assertTrue(is_denied(self.guard(role, "Write", file_path=str(self.tmp / ".venture/gates/G1.json"))))

    def test_g3_needs_exploratory_and_autopilot_labels(self):
        self.g1_ready()
        self.wait_for("G1")
        self.stop()
        self.art("release-report")
        self.art("redteam", name="g3", gate="G3")
        self.put(".venture/state/autopilot-decisions.md", "## G1\nx\n## G3\ny\n")
        probs = sw.gate_problems(self.v, "G3")
        self.assertTrue(any("EXPLORATORY" in p for p in probs))
        self.assertTrue(any("AUTOPILOT" in p for p in probs))
        rp = self.v / "artifacts" / "release-report" / "a.md"
        rp.write_text(rp.read_text() + "\nEXPLORATORY AUTOPILOT: no human reviewed any gate.\n")
        self.assertEqual(sw.gate_problems(self.v, "G3"), [])

    def test_human_approval_still_works_in_god_mode(self):
        self.g1_ready()
        self.put(".venture/state/autopilot-decisions.md", "## G1\nx\n")
        self.assertIn("recorded approved for G1", self.prompt("approve G1")[1])
        self.assertEqual(sw.gate_by(self.v, "G1"), "human")


    def run_cli(self, name, *args):
        out = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                sw.CLI[name](list(args))
            except SystemExit as e:
                code = e.code or 0
                if isinstance(e.code, str):
                    out.write(e.code)
        return code, out.getvalue()

    def test_cli_gates_refused_on_hook_enforced_runs(self):
        self.g1_ready()
        code, out = self.run_cli("autopilot", "G1")
        self.assertTrue(code)
        self.assertIn("hook-enforced", out)
        self.assertFalse(sw.gate_ok(self.v, "G1"))
        self.assertTrue(self.run_cli("approve", "G1")[0])

    def test_cli_gates_on_sequential_runs(self):
        with contextlib.redirect_stdout(io.StringIO()):
            sw.cmd_init(["--preset", "lean", "--mode", "god", "--sequential", "--dir", str(self.tmp), "--brief-text", "b", "--force"])
        self.g1_ready(log=False)
        self.assertIn("refused", self.run_cli("autopilot", "G1")[1])
        self.put(".venture/state/autopilot-decisions.md", "## G1\nx\n")
        self.assertIn("recorded G1", self.run_cli("autopilot", "G1")[1])
        self.assertEqual(sw.gate_by(self.v, "G1"), "autopilot")

    def test_bash_guard_blocks_gate_cli_for_agents(self):
        for c in ("python swarm.py autopilot G1", "python swarm.py approve G2", "python swarm.py init --sequential --force"):
            self.assertTrue(is_denied(self.guard("engineer-senior", "Bash", command=c)))


class TestSecrets(Base):
    def test_agents_cannot_touch_env_files(self):
        for role in ("engineer-senior", "qa", "strategy-head", "orchestrator", "auditor"):
            for name in (".env", ".env.local", ".env.production", "config/.env", "deploy/key.pem"):
                self.assertTrue(is_denied(self.guard(role, "Read", file_path=str(self.tmp / name))), (role, name))
        for name in (".env", ".env.local"):
            self.assertTrue(is_denied(self.guard("engineer-senior", "Write", file_path=str(self.tmp / name), content="K=v")))
            self.assertTrue(is_denied(self.guard("engineer-senior", "Edit", file_path=str(self.tmp / name))))

    def test_env_example_is_allowed(self):
        for name in (".env.example", ".env.sample", ".env.template"):
            self.assertFalse(is_denied(self.guard("engineer-senior", "Write", file_path=str(self.tmp / name), content="KEY=")))
            self.assertFalse(is_denied(self.guard("engineer-senior", "Read", file_path=str(self.tmp / name))))

    def test_bash_cannot_mention_env_files(self):
        b = lambda c: is_denied(self.guard("engineer-senior", "Bash", command=c))
        for c in ("cat .env", "source .env && pytest", "cp .env.example .env", "grep KEY .env.local", "docker run --env-file=.env x", "echo K=v >> .env", "cat ~/.ssh/id_rsa"):
            self.assertTrue(b(c), c)
        for c in ("cp .env.example .env.example.bak", "node -e console.log(process.env.HOME)", "pytest -q", "echo $os.environ", "ls .environment"):
            self.assertFalse(b(c), c)

    def test_ci_live_loads_env_and_masks_output(self):
        self.put(".env", "# comment\nexport API_KEY='sk-secret-12345'\nSHORT=ab\nOTHER=\"value-0000\"\n")
        sw.save_json(self.v / "runtime" / "tests.lock.json", {"hash": sw.tests_state(self.v)[0]})
        prog = "import os;print(os.environ.get('API_KEY'), os.environ.get('OTHER'))"
        for live, expect in ((False, "None None"), (True, "*** ***")):
            args = ["--task", "S1"] + (["--live"] if live else []) + ["--", sys.executable, "-c", prog]
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):
                    sw.cmd_ci(args)
            rec = sw.load_json(self.v / "work" / "S1" / "ci.json")
            self.assertIn(expect, rec["output_tail"])
            self.assertNotIn("sk-secret-12345", json.dumps(rec))
            self.assertEqual(rec["live"], live)


class TestConfigConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = sw.roles()
        cls.roster = sw.cfg("roster")
        cls.stages = sw.cfg("stages")
        cls.schemas = sw.cfg("schemas")

    def test_presets_reference_real_roles(self):
        for name, p in self.roster["presets"].items():
            for r in p["roles"]:
                self.assertIn(r, self.R, (name, r))
            for r, a in p["absorb"].items():
                self.assertIn(r, self.R)
                self.assertIn(a, p["roles"], (name, r, a))
            self.assertEqual(sorted(set(p["roles"]) | set(p["absorb"])), sorted(k for k in self.R if k != "orchestrator"), name)

    def test_absorbers_can_do_absorbed_work(self):
        lean = self.roster["presets"]["lean"]
        for r, a in lean["absorb"].items():
            ra, aa = self.R[r], self.R[a]
            self.assertTrue(set(ra["stages"]) <= set(aa["stages"]) or "*" in aa["stages"], (r, a, "stages"))
            self.assertTrue(set(ra["tools"]) <= set(aa["tools"]), (r, a, "tools"))
            self.assertTrue(set(ra["writes"]) <= set(aa["writes"]), (r, a, "writes", set(ra["writes"]) - set(aa["writes"])))

    def test_stages_gates_and_artifact_types_exist(self):
        for r, spec in self.R.items():
            for s in spec["stages"]:
                self.assertTrue(s == "*" or s in self.stages["stages"], (r, s))
            self.assertIn(spec["tier"], sw.cfg("models")["tiers"])
        for g in self.stages["gates"].values():
            for req in g["artifacts"]:
                self.assertIn(req["type"], self.schemas)
        for s in self.stages["stages"].values():
            for g in s["requires"]:
                self.assertIn(g, self.stages["gates"])

    def test_every_gate_artifact_has_a_writer(self):
        for g in self.stages["gates"].values():
            for req in g["artifacts"]:
                path = ".venture/artifacts/%s/x.md" % req["type"]
                self.assertTrue(any(sw.allowed(sw.expand(spec["writes"], []), path) for spec in self.R.values()), req)

    def test_skills_exist(self):
        have = {p.parent.name for p in (ROOT / "adapters" / "claude" / "skills").glob("*/SKILL.md")}
        for p in (ROOT / "core" / "agents").glob("*.md"):
            text = p.read_text()
            for line in text.split("\n"):
                if line.startswith(("skills:", "optional_skills:")):
                    for s in json.loads(line.split(":", 1)[1]):
                        self.assertIn(s, have, (p.name, s))

    def test_engineers_and_qa_partition_tests(self):
        tests = sw.cfg("limits")["test_globs"]
        for r in ("engineer-senior", "engineer-junior"):
            self.assertFalse(sw.allowed(sw.expand(self.R[r]["writes"], tests), "tests/test_x.py"))
            self.assertFalse(sw.allowed(sw.expand(self.R[r]["writes"], tests), "src/a.spec.ts"))
            self.assertTrue(sw.allowed(sw.expand(self.R[r]["writes"], tests), "src/a.ts"))
        self.assertTrue(sw.allowed(sw.expand(self.R["qa"]["writes"], tests), "src/a.spec.ts"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
