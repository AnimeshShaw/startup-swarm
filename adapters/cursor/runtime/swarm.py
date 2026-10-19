#!/usr/bin/env python3
"""Swarm runtime: hook handlers, CI wrapper, validator, ledger. Stdlib only.

Hook subcommands read the host's hook JSON on stdin:
  prompt | dispatch | guard | after-task | post-write | stop | substop
CLI subcommands: init | status | validate | ci | diff
Hosts without hooks (sequential runs, init --sequential) also get: approve | reject | pause | resume | end | autopilot
"""
import contextlib
import functools
import hashlib
import io
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
DATA = pathlib.Path(os.environ.get("SWARM_DATA") or (PLUGIN_ROOT / "data"))

HARD_WRITE_DENY = [".venture/gates/**", ".venture/ledger.jsonl", ".venture/runtime/**",
                   ".venture/work/*/ci.json", ".venture/work/*/diff.patch", ".git/**", ".claude/**"]
STATE_WRITE = ".venture/state/**"
SECRET_PATH = re.compile(r"(?:^|/)(?:\.env(?:\.[^/]+)?|[^/]+\.pem|id_rsa|id_ed25519)$", re.I)
SECRET_SAFE = re.compile(r"\.env\.(?:example|sample|template|dist)(?:\.[\w\-]+)?$", re.I)
SECRET_WORD = re.compile(r"(?<![\w.\-])\.env(?:\.[\w.\-]+)?(?![\w.\-])", re.I)
READ_T = {"Read", "Grep", "Glob", "NotebookRead"}
WRITE_T = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
WEB_T = {"WebFetch", "WebSearch"}
CLAIM = re.compile(r"\[(FACT|ESTIMATE|GUESS)([^\]]*)\]")


# ---------------------------------------------------------------- utilities
def now():
    return time.time()


def iso(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t if t else now()))


def load_json(p, default=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(p, obj):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + "." + uuid.uuid4().hex[:6] + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def cfg(name):
    return load_json(DATA / (name + ".json"), {})


def roles():
    return cfg("roles")


@contextlib.contextmanager
def locked(path, timeout=5.0):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = str(path) + ".lock"
    end = now() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if now() > end:
                try:
                    os.remove(lock)
                except OSError:
                    pass
            else:
                time.sleep(0.03)
    try:
        yield
    finally:
        os.close(fd)
        try:
            os.remove(lock)
        except OSError:
            pass


def find_vdir(cwd=None):
    p = pathlib.Path(cwd or os.getcwd()).resolve()
    for d in [p] + list(p.parents):
        rj = d / ".venture" / "runtime" / "run.json"
        if rj.exists():
            return (d / ".venture") if (load_json(rj, {}).get("active")) else None
    return None


def log(vdir, event, **kw):
    rec = {"ts": iso(), "t": round(now(), 3), "event": event}
    rec.update(kw)
    try:
        with open(pathlib.Path(vdir) / "ledger.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def rel(root, p):
    try:
        ap = os.path.abspath(p if os.path.isabs(p) else os.path.join(str(root), p))
        r = pathlib.Path(ap).relative_to(pathlib.Path(str(root))).as_posix()
        return "" if r == "." else r
    except ValueError:
        return None


def is_under(p, base):
    try:
        pathlib.Path(os.path.abspath(p)).relative_to(pathlib.Path(str(base)).resolve())
        return True
    except ValueError:
        return False


@functools.lru_cache(maxsize=512)
def _rx(pat):
    i, out = 0, ""
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.compile("^" + out + "$", re.I)  # case-insensitive: Windows and macOS file systems are


def gmatch(pat, path):
    if pat.endswith("/**") and _rx(pat[:-3]).match(path):
        return True
    return bool(_rx(pat).match(path))


def expand(pats, tests):
    out = []
    for p in pats:
        neg = p.startswith("!")
        q = p[1:] if neg else p
        if q == "@tests":
            out += [("!" if neg else "") + t for t in tests]
        else:
            out.append(p)
    return out


def allowed(pats, path):
    """gitignore-style: ordered patterns, '!' negates, last match wins."""
    res = False
    for p in pats:
        neg = p.startswith("!")
        if gmatch(p[1:] if neg else p, path):
            res = not neg
    return res


def is_secret(path):
    """.env files and private keys: agents never read or write them. .env.example and friends are fine."""
    return bool(SECRET_PATH.search(path)) and not SECRET_SAFE.search(path)


def hard_denied(path, role):
    pats = list(HARD_WRITE_DENY)
    if role != "orchestrator":
        pats.append(STATE_WRITE)
    return any(gmatch(p, path) for p in pats)


def literal_prefix(p):
    m = re.search(r"[*?]", p)
    return p[: m.start()] if m else p


def overlaps_denied(r, pats):
    d = (r.strip("/") + "/") if r else ""
    for p in pats:
        if not p.startswith("!"):
            continue
        pre = literal_prefix(p[1:])
        if pre and (pre.startswith(d) or d.startswith(pre)):
            return True
    return False


def norm_role(name):
    return name.split(":")[-1].strip() if name else None


def header(prompt, key):
    m = re.search(r"^\s*" + key + r"\s*:\s*(\S+)", prompt or "", re.I | re.M)
    return m.group(1) if m else None


def parse_front(text):
    text = text.replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).split("\n"):
        k, sep, v = line.partition(":")
        if sep and k.strip() and not line.startswith(" "):
            fm[k.strip()] = v.strip().strip("\"'")
    return fm, m.group(2)


# ---------------------------------------------------------------- run state
def run_state(vdir):
    return load_json(vdir / "runtime" / "run.json", {})


def plan_state(vdir):
    return load_json(vdir / "state" / "plan.json", {})


def key_path(run_id):
    return pathlib.Path(os.path.expanduser("~")) / ".swarm" / "keys" / run_id


def sign(vdir, gate, status, at, by="human"):
    try:
        key = key_path(run_state(vdir).get("id", "")).read_text()
    except OSError:
        key = ""
    return hashlib.sha256((key + "|" + gate + "|" + status + "|" + at + "|" + by).encode()).hexdigest()


def is_god(vdir):
    return run_state(vdir).get("mode") == "god"


def gate_by(vdir, g):
    """Who recorded this gate: 'human', 'autopilot' (god mode only) or None if absent/forged."""
    d = load_json(vdir / "gates" / (g + ".json"), {})
    by = d.get("by")
    if by not in ("human", "autopilot") or (by == "autopilot" and not is_god(vdir)):
        return None
    if d.get("sig") != sign(vdir, g, d.get("status", ""), d.get("at", ""), by):
        return None
    return by


def gate_status(vdir, g):
    if not gate_by(vdir, g):
        return None
    return load_json(vdir / "gates" / (g + ".json"), {}).get("status")


def gate_ok(vdir, g):
    return gate_status(vdir, g) in ("approved", "exploratory")


def counters(vdir):
    return load_json(vdir / "runtime" / "counters.json", {"dispatches": {}, "attempts": {}, "tokens_by_src": {}, "stage_first": {}})


def active_state(vdir):
    a = load_json(vdir / "runtime" / "active.json", {})
    t = now()
    return {r: [x for x in v if t - x < 7200] for r, v in a.items()}


def resolve_roles(inp, vdir):
    at = norm_role(inp.get("agent_type"))
    if at:
        return [at]
    act = [r for r, v in active_state(vdir).items() if v]
    return act or ["orchestrator"]


# ---------------------------------------------------------------- artifacts
def art_files(vdir, typ):
    d = vdir / "artifacts" / typ
    return sorted(d.glob("*.md")) if d.exists() else []


def read_text(p):
    try:
        return pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def validate_artifact(path, typ, structural=True):
    S = cfg("schemas")
    sch = S.get(typ)
    if not isinstance(sch, dict) or typ.startswith("_"):
        return ["unknown artifact type '%s'" % typ]
    fm, body = parse_front(read_text(path))
    errs = []
    for k in S["_common_front"] + sch.get("extra_front", []):
        if not fm.get(k):
            errs.append("front matter missing '%s'" % k)
    if fm.get("type") and fm["type"] != typ:
        errs.append("front matter type is '%s', expected '%s'" % (fm["type"], typ))
    if fm.get("status") and fm["status"] not in S["_status_values"]:
        errs.append("status must be draft or final")
    if not structural:
        return errs
    for k, vals in sch.get("enums", {}).items():
        if fm.get(k) and fm[k] not in vals:
            errs.append("'%s' must be one of %s" % (k, vals))
    for h in sch.get("headings", []):
        if not re.search(r"^#{2,3}\s*" + re.escape(h) + r"\b", body, re.I | re.M):
            errs.append("missing section '## %s'" % h)
    words = len(body.split())
    if words < sch.get("min_words", 0):
        errs.append("too short (%d words, need %d)" % (words, sch["min_words"]))
    if sch.get("max_words") and words > sch["max_words"]:
        errs.append("too long (%d words, max %d)" % (words, sch["max_words"]))
    if sch.get("claims"):
        tags = CLAIM.findall(body)
        need = sch.get("min_claims", 1)
        if len(tags) < need:
            errs.append("needs >= %d tagged claims ([FACT src=..] [ESTIMATE basis=..] [GUESS]); found %d" % (need, len(tags)))
        for kind, rest in tags:
            if kind == "FACT" and not re.search(r"src=\S+", rest):
                errs.append("a [FACT] tag has no src=")
            if kind == "ESTIMATE" and not re.search(r"basis=\S+", rest):
                errs.append("an [ESTIMATE] tag has no basis=")
    for pat in sch.get("patterns", []):
        found = {m.group(0) for m in re.finditer(pat["regex"], body)}
        if len(found) < pat.get("min", 1):
            errs.append(pat.get("msg", "pattern %s missing" % pat["regex"]))
    seen, out = set(), []
    for e in errs:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def find_artifacts(vdir, req, final=True):
    out = []
    for p in art_files(vdir, req["type"]):
        fm, _ = parse_front(read_text(p))
        if req.get("gate") and fm.get("gate") != req["gate"]:
            continue
        if final and fm.get("status") != "final":
            continue
        out.append(p)
    return out


def open_blocking(vdir):
    n = 0
    qd = vdir / "questions"
    if qd.exists():
        for p in qd.glob("*.md"):
            fm, _ = parse_front(read_text(p))
            if fm.get("blocking", "").lower() == "true" and fm.get("status", "open").lower() == "open":
                n += 1
    return n


def gate_problems(vdir, g):
    ST = cfg("stages")
    out = []
    for req in ST["gates"][g]["artifacts"]:
        label = req["type"] + (" (%s)" % req["gate"] if req.get("gate") else "")
        files = find_artifacts(vdir, req, final=True)
        if not files:
            out.append("missing final artifact: " + label)
            continue
        for p in files:
            out += ["%s: %s" % (p.name, e) for e in validate_artifact(p, req["type"])]
    n = open_blocking(vdir)
    if n:
        out.append("%d blocking question(s) still open in .venture/questions/" % n)
    if g == "G3" and gate_status(vdir, "G1") == "exploratory":
        reps = find_artifacts(vdir, {"type": "release-report"}, final=True)
        if not any("EXPLORATORY" in read_text(p) for p in reps):
            out.append("G1 was waived as exploratory: release-report must say EXPLORATORY")
    if is_god(vdir):
        log_p = vdir / "state" / "autopilot-decisions.md"
        if not re.search(r"(?m)^##\s*%s\b" % g, read_text(log_p)):
            out.append("god mode: .venture/state/autopilot-decisions.md needs a '## %s' section (decisions, assumptions, accepted risks, confidence)" % g)
        if g == "G3":
            reps = find_artifacts(vdir, {"type": "release-report"}, final=True)
            if not any("AUTOPILOT" in read_text(p) for p in reps):
                out.append("god mode: release-report must say AUTOPILOT and state that no human reviewed any gate")
    return out


def autopilot_gate(vdir, g):
    """God mode only: record a gate on the orchestrator's behalf when its checks pass. Returns the list of problems."""
    if not is_god(vdir):
        return ["autopilot gates exist only in god mode"]
    probs = gate_problems(vdir, g)
    if probs:
        return probs
    status = "exploratory" if g == "G1" else "approved"
    at = iso()
    save_json(vdir / "gates" / (g + ".json"), {"gate": g, "status": status, "by": "autopilot", "at": at, "sig": sign(vdir, g, status, at, "autopilot")})
    log(vdir, "gate", gate=g, status=status, by="autopilot")
    return []


def trace_gap(vdir):
    prds = art_files(vdir, "prd")
    if not prds:
        return []
    ids, cov = set(), set()
    for p in prds:
        ids |= set(re.findall(r"AC-\d+", read_text(p)))
    for p in art_files(vdir, "test-plan"):
        cov |= set(re.findall(r"AC-\d+", read_text(p)))
    return sorted(ids - cov)


# ---------------------------------------------------------------- tests lock
def hash_tests(root, globs, skip):
    files = []
    for dp, dn, fn in os.walk(str(root)):
        dn[:] = [d for d in dn if d not in skip]
        for f in fn:
            r = rel(root, os.path.join(dp, f))
            if r and any(gmatch(g, r) for g in globs):
                files.append(r)
    h = hashlib.sha256()
    for r in sorted(files):
        h.update(r.encode())
        try:
            h.update(hashlib.sha256(pathlib.Path(root, r).read_bytes()).digest())
        except OSError:
            pass
    return h.hexdigest(), len(files)


def tests_state(vdir):
    L = cfg("limits")
    return hash_tests(vdir.parent, L["test_globs"], set(L["hash_skip_dirs"]))


# ---------------------------------------------------------------- tool guard
def bash_targets(cmd):
    """Best-effort list of paths a shell command writes to. Tracks `cd` so relative targets resolve."""
    out, prefix = [], ""
    for seg in re.split(r"&&|\|\||;|\||\n", cmd):
        try:
            toks = shlex.split(seg, posix=True)
        except ValueError:
            toks = seg.split()
        t = [m.group(1) for m in re.finditer(r"(?:^|[\s;|&])\d*>>?\s*([^\s;|&<>]+)", seg)]
        if toks:
            c = os.path.basename(toks[0]).lower()
            args = [a for a in toks[1:] if not a.startswith("-")]
            if c == "cd":
                if args and not args[0].startswith(("~", "$", "-")):
                    prefix = args[0] if os.path.isabs(args[0]) else os.path.normpath(os.path.join(prefix, args[0]))
                continue
            if c in ("rm", "mv", "cp", "tee", "touch", "mkdir", "ln", "truncate", "rmdir", "del", "copy", "move", "install", "chmod"):
                t += args
            elif c == "sed" and any(a.startswith("-i") or a == "--in-place" for a in toks[1:]):
                t += args
            elif c == "git" and len(toks) > 1 and toks[1] in ("checkout", "restore", "apply", "reset", "stash", "clean", "rm", "mv", "revert", "cherry-pick", "merge", "rebase", "pull"):
                t += args
        out += [x if (not prefix or os.path.isabs(x)) else os.path.join(prefix, x) for x in t]
    return out


RUNTIME = HERE / "swarm.py"
RT_TOKEN = re.compile(r"\"([^\"]*swarm\.py)\"|'([^']*swarm\.py)'|(\S*swarm\.py)")


def strip_runtime(cmd):
    """Remove this plugin's own runtime path from a command before the protected-path check.
    Marketplace installs live under ~/.claude/, which would otherwise make every `swarm.py ci` call look
    like an access to .claude/. Only a token that resolves to exactly this file is removed."""
    def sub(m):
        tok = os.path.expandvars(m.group(1) or m.group(2) or m.group(3))
        try:
            same = pathlib.Path(tok).expanduser().resolve() == RUNTIME.resolve()
        except (OSError, ValueError):
            same = False
        return " " if same else m.group(0)
    return RT_TOKEN.sub(sub, cmd)


def check_bash(role, spec, cmd, root, tests):
    if "swarm.py" in cmd and not re.search(r"swarm\.py[\"']?\s+(ci|diff|validate|status)\b", cmd):
        return "runtime control commands are not available to agents"
    if re.search(r"\.venture[\\/]+(gates|state|runtime|ledger)|\.claude[\\/]|\.git[\\/]+(hooks|config)|\.swarm\b", strip_runtime(cmd), re.I):
        return "that path is protected"
    for m in SECRET_WORD.finditer(cmd):
        if not SECRET_SAFE.search(m.group(0)):
            return "secrets stay out of agent reach: put real values in .env yourself, and ask the human through a question of kind: secret. .env.example is allowed"
    if re.search(r"\bid_(?:rsa|ed25519)\b|\.pem\b", cmd):
        return "private keys are out of agent reach"
    if re.search(r"\brm\s+(?:-\S+\s+)*(?:\.|\./|\*|\./\*|/|~)(?:\s|$)", cmd):
        return "refusing to remove the project root or everything in it"
    wpats = expand(spec["writes"], tests)
    cmds = [cmd]
    m = re.search(r"swarm\.py[\"']?\s+ci\b.*?\s--\s(.*)$", cmd, re.S)
    if m:
        cmds.append(m.group(1))
    for c in cmds:
        for tgt in bash_targets(c):
            r = rel(root, tgt.strip("\"'"))
            if not r:
                continue
            if hard_denied(r, role) or not allowed(wpats, r):
                return "%s may not modify %s" % (role, r)
    return None


def check(role, tool, ti, root, spec, tests):
    if spec is None:
        return None if tool in READ_T else "unknown role '%s' may not use %s" % (role, tool)
    tools = set(spec["tools"])
    if tool in READ_T:
        if "read" not in tools:
            return "%s has no read access" % role
        p = ti.get("file_path") or ti.get("path") or "."
        r = rel(root, p)
        if r is None:
            return None if is_under(p, PLUGIN_ROOT) else "%s may not read outside the project: %s" % (role, p)
        pats = expand(spec["reads"], tests)
        if r and is_secret(r):
            return "%s may not read %s: secrets stay out of agent reach (use .env.example for names)" % (role, r)
        if r and not allowed(pats, r):
            return "%s may not read %s (isolation rule)" % (role, r)
        if tool in ("Grep", "Glob") and overlaps_denied(r, pats):
            return "%s: this search would cover files you are isolated from; scope it to a subdirectory such as src/, tests/ or .venture/artifacts/" % role
        return None
    if tool in WRITE_T:
        if "write" not in tools:
            return "%s cannot write files" % role
        p = ti.get("file_path") or ti.get("notebook_path") or ""
        r = rel(root, p)
        if r is None:
            return "%s may not write outside the project" % role
        if hard_denied(r, role):
            return "%s is a protected path" % r
        if is_secret(r):
            return "%s may not write %s: the human creates .env; agents write .env.example" % (role, r)
        if not allowed(expand(spec["writes"], tests), r):
            return "%s may not write %s: it is outside this role's write scope (see your role file). If it needs changing, write a question in .venture/questions/." % (role, r)
        return None
    if tool == "Bash":
        if "bash" not in tools:
            return "%s has no shell access" % role
        return check_bash(role, spec, ti.get("command", ""), root, tests)
    if tool in WEB_T:
        return None if "web" in tools else "%s has no web access" % role
    return None


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "[swarm] " + reason}}))
    sys.exit(0)


def fail(msg):
    sys.stderr.write("[swarm] " + msg + "\n")
    sys.exit(2)


def cmd_guard(inp):
    vdir = find_vdir(inp.get("cwd"))
    if not vdir:
        return
    root = vdir.parent
    tool = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    R = roles()
    tests = cfg("limits").get("test_globs", [])
    for role in resolve_roles(inp, vdir):
        why = check(role, tool, ti, root, R.get(role), tests)
        if why:
            log(vdir, "deny", role=role, tool=tool, why=why)
            deny(why)


# ---------------------------------------------------------------- dispatch gate
def cmd_dispatch(inp):
    vdir = find_vdir(inp.get("cwd"))
    if not vdir:
        return
    ti = inp.get("tool_input") or {}
    role = norm_role(ti.get("subagent_type"))
    R, ST, L = roles(), cfg("stages"), cfg("limits")
    run = run_state(vdir)
    preset = cfg("roster")["presets"].get(run.get("preset"), {})
    if role not in R or role == "orchestrator":
        deny("only swarm roles can be dispatched (got '%s'). Roles: %s" % (role, ", ".join(sorted(k for k in R if k != "orchestrator"))))
    if role not in preset.get("roles", []):
        a = preset.get("absorb", {}).get(role)
        sk = preset.get("absorb_skills", {}).get(role)
        hint = (" Dispatch '%s' instead and put 'SKILLS: swarm:%s' in the prompt." % (a, sk)) if a and sk else (" Dispatch '%s' instead." % a if a else "")
        deny("role '%s' is not in preset '%s'.%s" % (role, run.get("preset"), hint))
    prompt = ti.get("prompt", "")
    task, stage = header(prompt, "TASK"), header(prompt, "STAGE")
    if not task or not stage:
        deny("the dispatch prompt must contain header lines 'TASK: <id>' and 'STAGE: <stage>'")
    if stage not in ST["stages"]:
        deny("unknown stage '%s'. Stages: %s" % (stage, ", ".join(ST["stages"])))
    spec = R[role]
    if "*" not in spec["stages"] and stage not in spec["stages"]:
        deny("role '%s' does not work in stage '%s' (allowed: %s)" % (role, stage, ", ".join(spec["stages"])))
    sdef = ST["stages"][stage]
    for g in sdef.get("requires", []):
        if not gate_ok(vdir, g):
            if is_god(vdir):
                deny("stage '%s' needs gate %s. God mode: finish the gate artifacts and the '## %s' section in .venture/state/autopilot-decisions.md, set plan.waiting to \"%s\" and end your turn; autopilot records the gate." % (stage, g, g, g))
            deny("stage '%s' needs gate %s approved by the human. Set plan waiting and ask the user to type: approve %s" % (stage, g, g))
    for req in sdef.get("requires_artifacts", []):
        if not find_artifacts(vdir, req, final=True):
            deny("stage '%s' needs a final '%s' artifact first" % (stage, req["type"]))
    if role in ST.get("needs_test_lock", []) and not load_json(vdir / "runtime" / "tests.lock.json"):
        deny("QA must write and lock the tests before engineers start (dispatch qa for this sprint first)")
    key = task + "|" + role
    with locked(vdir / "runtime" / "counters.json"):
        c = counters(vdir)
        act = active_state(vdir)
        cap = preset.get("spawn_caps", {}).get(role, spec.get("max_instances", 1))
        if len(act.get(role, [])) >= cap:
            deny("spawn cap reached for '%s' (%d running). Wait for one to finish." % (role, cap))
        if sum(len(v) for v in act.values()) >= L.get("max_parallel_total", 6):
            deny("global parallelism cap reached")
        if c["attempts"].get(key, 0) >= L.get("max_attempts_per_task_role", 3):
            deny("task %s has used %d attempts with '%s'. Stop retrying: escalate to the human via a blocking question." % (task, c["attempts"][key], role))
        sb = L.get("stage_budgets", {}).get(stage, {})
        if sb.get("dispatches") and c["dispatches"].get(stage, 0) >= sb["dispatches"]:
            deny("dispatch budget for stage '%s' exhausted (%d). Escalate to the human." % (stage, sb["dispatches"]))
        if (now() - run.get("started", now())) / 60 > L["run"]["wall_minutes"]:
            deny("run wall-clock budget exhausted. Escalate to the human.")
        if sum(c["tokens_by_src"].values()) > L["run"]["tokens"]:
            deny("run token budget exhausted. Escalate to the human.")
        c["attempts"][key] = c["attempts"].get(key, 0) + 1
        c["dispatches"][stage] = c["dispatches"].get(stage, 0) + 1
        c["stage_first"].setdefault(stage, now())
        save_json(vdir / "runtime" / "counters.json", c)
        act.setdefault(role, []).append(now())
        save_json(vdir / "runtime" / "active.json", act)
    log(vdir, "dispatch", role=role, stage=stage, task=task, attempt=c["attempts"][key])


def cmd_after_task(inp):
    vdir = find_vdir(inp.get("cwd"))
    if not vdir:
        return
    ti = inp.get("tool_input") or {}
    role = norm_role(ti.get("subagent_type"))
    task = header(ti.get("prompt", ""), "TASK")
    with locked(vdir / "runtime" / "active.json"):
        a = load_json(vdir / "runtime" / "active.json", {})
        if a.get(role):
            a[role].pop(0)
        save_json(vdir / "runtime" / "active.json", a)
    log(vdir, "stop", role=role, task=task)
    ST = cfg("stages")
    if role == "qa":
        gap = trace_gap(vdir)
        if gap:
            fail("test-plan does not cover acceptance criteria %s. Tests are not locked; dispatch qa again." % ", ".join(gap))
        h, n = tests_state(vdir)
        save_json(vdir / "runtime" / "tests.lock.json", {"hash": h, "files": n, "at": iso()})
        log(vdir, "tests_locked", files=n)
    elif role in ST.get("test_verify_after", []):
        lock = load_json(vdir / "runtime" / "tests.lock.json")
        if lock:
            h, n = tests_state(vdir)
            if h != lock["hash"]:
                log(vdir, "tamper", role=role, task=task)
                fail("test files changed after QA locked them (by '%s', task %s). Revert test changes; this attempt counts as failed. If a test is wrong, write .venture/work/<task>/test-dispute.md for QA." % (role, task))


def cmd_post_write(inp):
    vdir = find_vdir(inp.get("cwd"))
    if not vdir:
        return
    ti = inp.get("tool_input") or {}
    r = rel(vdir.parent, ti.get("file_path") or "")
    if not r:
        return
    m = re.match(r"^\.venture/artifacts/([^/]+)/[^/]+\.md$", r)
    if not m:
        return
    typ = m.group(1)
    fm, _ = parse_front(read_text(vdir.parent / r))
    errs = validate_artifact(vdir.parent / r, typ, structural=(fm.get("status") == "final"))
    if errs:
        log(vdir, "invalid_artifact", path=r, n=len(errs))
        fail("%s failed validation:\n- %s\nFix and rewrite the file (status: draft skips structure checks until you set final)." % (r, "\n- ".join(errs)))


# ---------------------------------------------------------------- human-facing hooks
APPROVE = re.compile(r"^\s*/?(?:swarm:)?approve\s+(G[123])(?:\s+(exploratory))?\s*$", re.I)
REJECT = re.compile(r"^\s*/?(?:swarm:)?reject\s+(G[123])\b\s*(.*)$", re.I | re.S)
CTRL = re.compile(r"^\s*/?(?:swarm:)?(pause|resume|end)\s*$", re.I)


def ctx(text, event="UserPromptSubmit"):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


def status_line(vdir):
    plan = plan_state(vdir)
    gs = " ".join("%s=%s" % (g, gate_status(vdir, g) or "-") for g in ("G1", "G2", "G3"))
    env = "present" if (vdir.parent / ".env").is_file() else "absent"
    return "[swarm] mode=%s stage=%s gates: %s open-blocking-questions=%d waiting=%s env-file=%s runtime=%s" % (run_state(vdir).get("mode", "guided"), plan.get("stage", "discover"), gs, open_blocking(vdir), plan.get("waiting") or "no", env, HERE / "swarm.py")


def find_ended(cwd=None):
    """The .venture of a run that was ended with `end` (run.json present, active false), else None."""
    p = pathlib.Path(cwd or os.getcwd()).resolve()
    for d in [p] + list(p.parents):
        rj = d / ".venture" / "runtime" / "run.json"
        if rj.exists():
            return (d / ".venture") if not load_json(rj, {}).get("active") else None
    return None


def cmd_prompt(inp):
    vdir = find_vdir(inp.get("cwd"))
    text = inp.get("prompt", "") or ""
    if not vdir:
        # Only a message the human types can bring an ended run back; agents cannot produce this hook event.
        m = CTRL.match(text)
        ended = find_ended(inp.get("cwd")) if m and m.group(1).lower() == "resume" else None
        if ended:
            run = run_state(ended)
            run["active"] = True
            save_json(ended / "runtime" / "run.json", run)
            plan = plan_state(ended)
            plan["waiting"] = None
            save_json(ended / "state" / "plan.json", plan)
            log(ended, "run_resumed")
            ctx("[swarm] ended run reactivated by the human; continue from plan.next. " + status_line(ended))
        return
    m = APPROVE.match(text)
    if m:
        g = m.group(1).upper()
        exploratory = bool(m.group(2))
        ST = cfg("stages")
        if exploratory and not ST["gates"][g].get("allow_exploratory"):
            print(json.dumps({"decision": "block", "reason": "[swarm] only G1 can be approved as exploratory"}))
            return
        probs = [] if exploratory else gate_problems(vdir, g)
        if exploratory:
            probs = [p for p in gate_problems(vdir, g) if p.startswith("%d blocking" % open_blocking(vdir))]
        if probs:
            log(vdir, "approve_refused", gate=g, n=len(probs))
            print(json.dumps({"decision": "block", "reason": "[swarm] cannot approve %s yet:\n- %s" % (g, "\n- ".join(probs))}))
            return
        status = "exploratory" if exploratory else "approved"
        at = iso()
        save_json(vdir / "gates" / (g + ".json"), {"gate": g, "status": status, "by": "human", "at": at, "sig": sign(vdir, g, status, at)})
        log(vdir, "gate", gate=g, status=status)
        ctx("[swarm] Human recorded %s for %s. Continue the run." % (status, g))
        return
    m = REJECT.match(text)
    if m:
        g = m.group(1).upper()
        (vdir / "state").mkdir(parents=True, exist_ok=True)
        (vdir / "state" / ("feedback-%s.md" % g)).write_text(m.group(2).strip() or "(no reason given)", encoding="utf-8")
        try:
            os.remove(vdir / "gates" / (g + ".json"))
        except OSError:
            pass
        log(vdir, "gate_rejected", gate=g)
        ctx("[swarm] Human rejected %s. Read .venture/state/feedback-%s.md, plan the rework, continue." % (g, g))
        return
    m = CTRL.match(text)
    if m:
        c = m.group(1).lower()
        if c == "end":
            run = run_state(vdir)
            run["active"] = False
            save_json(vdir / "runtime" / "run.json", run)
            log(vdir, "run_ended")
            print(json.dumps({"decision": "block", "reason": "[swarm] run ended. Hooks are off; normal Claude Code behaviour restored."}))
            return
        plan = plan_state(vdir)
        plan["waiting"] = "user paused" if c == "pause" else None
        save_json(vdir / "state" / "plan.json", plan)
        log(vdir, c)
        ctx("[swarm] run %s by the human." % ("paused" if c == "pause" else "resumed; continue from plan.next"))
        return
    log(vdir, "human_prompt", chars=len(text))
    ctx(status_line(vdir))


def transcript_tokens(path):
    tot = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                u = (o.get("message") or {}).get("usage") or {}
                tot += int(u.get("input_tokens", 0) or 0) + int(u.get("output_tokens", 0) or 0)
    except OSError:
        return 0
    return tot


def record_tokens(vdir, path):
    if not path:
        return
    n = transcript_tokens(path)
    with locked(vdir / "runtime" / "counters.json"):
        c = counters(vdir)
        c["tokens_by_src"][str(path)] = n
        save_json(vdir / "runtime" / "counters.json", c)


def cmd_stop(inp):
    vdir = find_vdir(inp.get("cwd"))
    if not vdir:
        return
    record_tokens(vdir, inp.get("transcript_path"))
    plan, L, run = plan_state(vdir), cfg("limits"), run_state(vdir)
    stage = plan.get("stage", "discover")
    if stage == "done":
        return
    if (now() - run.get("started", now())) / 60 > L["run"]["wall_minutes"]:
        return
    god = run.get("mode") == "god"
    waiting = str(plan.get("waiting") or "")
    note = ""
    if god and waiting and waiting != "user paused":
        m = re.match(r"G[123]\b", waiting)
        plan["waiting"] = None
        if m:
            g = m.group(0)
            probs = [] if gate_ok(vdir, g) else autopilot_gate(vdir, g)
            if probs:
                plan["waiting"] = g
                note = "Autopilot cannot record %s yet:\n- %s\nFix these, then end your turn again. " % (g, "\n- ".join(probs))
            else:
                note = "Autopilot recorded %s. Continue with the next stage. " % g
        else:
            note = "God mode never waits for the human: answer your own question (record it in autopilot-decisions.md) and continue. "
        save_json(vdir / "state" / "plan.json", plan)
    elif waiting:
        return
    with locked(vdir / "runtime" / "continues.json"):
        cc = load_json(vdir / "runtime" / "continues.json", {})
        if cc.get(stage, 0) >= L.get("max_auto_continues_per_stage", 40):
            log(vdir, "continue_cap", stage=stage)
            return
        cc[stage] = cc.get(stage, 0) + 1
        save_json(vdir / "runtime" / "continues.json", cc)
    log(vdir, "auto_continue", stage=stage)
    if god:
        msg = "[swarm] " + note + "God mode: the run is active and you must not ask the human anything. Read .venture/state/plan.json and do plan.next now. At a gate, set plan.waiting to the gate id and end your turn."
    else:
        msg = "[swarm] The run is active and not waiting on the human. Read .venture/state/plan.json and do plan.next now. If you truly need the human (a gate or a blocking question), set plan.waiting to what you need and tell them exactly what to type."
    print(json.dumps({"decision": "block", "reason": msg}))


def cmd_substop(inp):
    vdir = find_vdir(inp.get("cwd"))
    if vdir:
        record_tokens(vdir, inp.get("agent_transcript_path") or inp.get("transcript_path"))


# ---------------------------------------------------------------- CLI commands
def summarize(vdir):
    ev = []
    try:
        with open(vdir / "ledger.jsonl", encoding="utf-8") as f:
            for line in f:
                try:
                    ev.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    run = run_state(vdir)
    c = counters(vdir)
    by = {}
    for e in ev:
        by.setdefault(e["event"], []).append(e)
    last = max([e["t"] for e in ev] + [run.get("started", now())])
    d_role = {}
    for e in by.get("dispatch", []):
        d_role[e["role"]] = d_role.get(e["role"], 0) + 1
    ci = by.get("ci", [])
    return {
        "preset": run.get("preset"),
        "mode": run.get("mode", "guided"),
        "autopilot_gates": sum(1 for e in by.get("gate", []) if e.get("by") == "autopilot"),
        "wall_minutes": round((last - run.get("started", last)) / 60, 1),
        "dispatches_total": len(by.get("dispatch", [])),
        "dispatches_by_role": d_role,
        "dispatches_by_stage": c.get("dispatches", {}),
        "tokens_known": sum(c.get("tokens_by_src", {}).values()),
        "guard_denies": len(by.get("deny", [])),
        "tamper_events": len(by.get("tamper", [])),
        "invalid_artifacts": len(by.get("invalid_artifact", [])),
        "human_prompts": len(by.get("human_prompt", [])),
        "gate_decisions": len(by.get("gate", [])) + len(by.get("gate_rejected", [])),
        "auto_continues": len(by.get("auto_continue", [])),
        "ci_runs": len(ci),
        "ci_passed": sum(1 for e in ci if e.get("passed")),
        "open_blocking_questions": open_blocking(vdir),
    }


def cmd_status(args):
    vdir = find_vdir()
    if not vdir:
        print("no active swarm run here")
        return
    print(status_line(vdir))
    print(json.dumps(summarize(vdir), indent=2))


def cmd_validate(args):
    vdir = find_vdir() or ((pathlib.Path(args[0]) / ".venture") if args else pathlib.Path.cwd() / ".venture")
    bad = 0
    ad = vdir / "artifacts"
    for d in sorted(ad.iterdir()) if ad.exists() else []:
        for p in sorted(d.glob("*.md")):
            fm, _ = parse_front(read_text(p))
            errs = validate_artifact(p, d.name, structural=(fm.get("status") == "final"))
            for e in errs:
                bad += 1
                print("%s/%s: %s" % (d.name, p.name, e))
    print("validate: %d problem(s)" % bad)
    sys.exit(1 if bad else 0)


def cmd_init(args):
    opts = {"--preset": cfg("roster").get("default_preset", "lean"), "--dir": os.getcwd(), "--brief-text": "", "--brief-file": "", "--mode": "guided"}
    sequential = "--sequential" in args
    force = "--force" in args
    i = 0
    while i < len(args):
        if args[i] in opts and i + 1 < len(args):
            opts[args[i]] = args[i + 1]
            i += 2
        else:
            i += 1
    if opts["--preset"] not in cfg("roster")["presets"]:
        sys.exit("unknown preset; choose from %s" % list(cfg("roster")["presets"]))
    if opts["--mode"] not in ("guided", "god"):
        sys.exit("unknown mode; choose guided or god")
    v = pathlib.Path(opts["--dir"]) / ".venture"
    rj = v / "runtime" / "run.json"
    if load_json(rj, {}).get("active") and not force:
        sys.exit("a run is already active here (use --force to restart)")
    for d in ("artifacts", "work", "state", "runtime", "gates", "questions"):
        (v / d).mkdir(parents=True, exist_ok=True)
    bf = opts["--brief-file"]
    brief = opts["--brief-text"] or ((sys.stdin.read() if bf == "-" else read_text(bf)) if bf else "")
    (v / "brief.md").write_text(brief or "(no brief given)", encoding="utf-8")
    run_id = uuid.uuid4().hex
    kp = key_path(run_id)
    kp.parent.mkdir(parents=True, exist_ok=True)
    kp.write_text(uuid.uuid4().hex + uuid.uuid4().hex)
    save_json(rj, {"active": True, "id": run_id, "preset": opts["--preset"], "mode": opts["--mode"], "sequential": sequential, "started": now(), "started_iso": iso()})
    save_json(v / "state" / "plan.json", {"stage": "discover", "next": "Dispatch strategy-head for the market brief (TASK: discover-1, STAGE: discover).", "waiting": None, "notes": []})
    for f in ("counters.json", "active.json", "continues.json", "tests.lock.json"):
        try:
            os.remove(v / "runtime" / f)
        except OSError:
            pass
    log(v, "init", preset=opts["--preset"], mode=opts["--mode"])
    print("swarm run initialised in %s (preset=%s, mode=%s); runtime=%s" % (v, opts["--preset"], opts["--mode"], HERE / "swarm.py"))


def load_dotenv(path):
    out = {}
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def cmd_ci(args):
    vdir = find_vdir()
    if "--" not in args or not vdir:
        sys.exit("usage: swarm.py ci --task <id> [--live] -- <command...>   (--live loads .env into the test process; output is masked)   (inside an active run)")
    k = args.index("--")
    opts, cmd = args[:k], args[k + 1:]
    task = opts[opts.index("--task") + 1] if "--task" in opts else "unspecified"
    L = cfg("limits")
    lock = load_json(vdir / "runtime" / "tests.lock.json")
    intact = None
    if lock:
        intact = tests_state(vdir)[0] == lock["hash"]
    t0 = now()
    env, secrets = dict(os.environ), []
    if "--live" in opts:
        for k, v in load_dotenv(vdir.parent / ".env").items():
            env.setdefault(k, v)
            if len(v) >= 6:
                secrets.append(v)
    try:
        cmdline = cmd[0] if len(cmd) == 1 else (subprocess.list2cmdline(cmd) if os.name == "nt" else shlex.join(cmd))
        p = subprocess.run(cmdline, shell=True, cwd=str(vdir.parent), capture_output=True, text=True, errors="replace", env=env, timeout=L.get("ci_timeout_seconds", 1800))
        code, out = p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        code, out = 124, "timeout"
    for sec in secrets:
        out = out.replace(sec, "***")
    tail = "\n".join(out.splitlines()[-200:])
    rec = {"task": task, "live": "--live" in opts, "command": cmdline, "exit_code": code, "passed": code == 0 and intact is not False, "tests_intact": intact, "duration_s": round(now() - t0, 1), "at": iso(), "output_tail": tail}
    save_json(vdir / "work" / task / "ci.json", rec)
    log(vdir, "ci", task=task, passed=rec["passed"], exit_code=code)
    print(tail[-3000:])
    print("[swarm ci] task=%s exit=%s tests_intact=%s passed=%s" % (task, code, intact, rec["passed"]))
    sys.exit(0 if rec["passed"] else (code or 1))


def cmd_diff(args):
    vdir = find_vdir()
    if not vdir or "--task" not in args:
        sys.exit("usage: swarm.py diff --task <id> [--base <ref>]")
    task = args[args.index("--task") + 1]
    base = args[args.index("--base") + 1] if "--base" in args else "HEAD~1"
    p = subprocess.run(["git", "diff", base, "HEAD"], cwd=str(vdir.parent), capture_output=True, text=True, errors="replace")
    d = vdir / "work" / task
    d.mkdir(parents=True, exist_ok=True)
    (d / "diff.patch").write_text(p.stdout, encoding="utf-8")
    log(vdir, "diff", task=task, bytes=len(p.stdout))
    print("wrote diff.patch (%d bytes)" % len(p.stdout))


HOOKS = {"prompt": cmd_prompt, "dispatch": cmd_dispatch, "guard": cmd_guard, "after-task": cmd_after_task,
         "post-write": cmd_post_write, "stop": cmd_stop, "substop": cmd_substop}
def cmd_gate_cli(name, args):
    """Hook-less hosts only: the human (or, in god mode, the agent) drives gates from a terminal."""
    vdir = find_vdir()
    if not vdir:
        sys.exit("no active swarm run here")
    if not run_state(vdir).get("sequential"):
        sys.exit("this run is hook-enforced; type the command in the chat instead: %s" % (name + " " + " ".join(args)).strip())
    if name == "autopilot":
        if not args:
            sys.exit("usage: autopilot G1|G2|G3")
        g = args[0].upper()
        probs = autopilot_gate(vdir, g)
        print("autopilot refused %s:\n- %s" % (g, "\n- ".join(probs)) if probs else "autopilot recorded %s" % g)
        return
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cmd_prompt({"cwd": str(vdir.parent), "prompt": (name + " " + " ".join(args)).strip()})
    for line in out.getvalue().splitlines():
        try:
            o = json.loads(line)
            print(o.get("reason") or o.get("hookSpecificOutput", {}).get("additionalContext", ""))
        except ValueError:
            print(line)


CLI = {"init": cmd_init, "status": cmd_status, "validate": cmd_validate, "ci": cmd_ci, "diff": cmd_diff,
       **{n: functools.partial(cmd_gate_cli, n) for n in ("approve", "reject", "pause", "resume", "end", "autopilot")}}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    name = sys.argv[1]
    if name in CLI:
        CLI[name](sys.argv[2:])
        return
    if name not in HOOKS:
        sys.exit("unknown subcommand " + name)
    try:
        inp = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        inp = {}
    try:
        HOOKS[name](inp)
    except SystemExit:
        raise
    except Exception as e:  # a crashing hook must not brick the session; record it
        v = find_vdir(inp.get("cwd"))
        if v:
            log(v, "hook_error", hook=name, error=repr(e))
        sys.stderr.write("[swarm] hook %s error: %r\n" % (name, e))


if __name__ == "__main__":
    main()
