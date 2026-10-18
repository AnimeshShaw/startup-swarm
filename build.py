#!/usr/bin/env python3
"""Generate adapters/claude, adapters/cursor, adapters/codex from core/. Never hand-edit adapters/<host>."""
import json
import pathlib
import re
import shutil

ROOT = pathlib.Path(__file__).resolve().parent
CORE = ROOT / "core"
OUT = ROOT / "adapters"
SRC = OUT / "_src"

TOOLMAP = {
    "read": ["Read", "Grep", "Glob"],
    "write": ["Write", "Edit", "MultiEdit"],
    "bash": ["Bash"],
    "web": ["WebSearch", "WebFetch"],
    "spawn": ["Task", "Agent"],
}


def split_front(text):
    text = text.replace("\r\n", "\n")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    return (m.group(1), m.group(2).strip()) if m else ("", text.strip())


def parse_agent(path):
    fm, body = split_front(path.read_text(encoding="utf-8"))
    meta = {}
    for line in fm.split("\n"):
        k, sep, v = line.partition(":")
        if not sep:
            continue
        v = v.strip()
        meta[k.strip()] = json.loads(v) if v.startswith("[") else (int(v) if v.isdigit() else v)
    meta["body"] = body
    return meta


def load_all():
    agents = {}
    for p in sorted((CORE / "agents").glob("*.md")):
        a = parse_agent(p)
        agents[a["id"]] = a
    skills = {}
    for p in sorted((CORE / "skills").glob("*/SKILL.md")):
        fm, body = split_front(p.read_text(encoding="utf-8"))
        d = dict(re.findall(r"^(\w+):\s*(.*)$", fm, re.M))
        skills[p.parent.name] = {"description": d.get("description", ""), "body": body}
    cfgs = {n: json.loads((CORE / "config" / (n + ".json")).read_text(encoding="utf-8")) for n in ("roster", "limits", "models", "stages", "schemas")}
    return agents, skills, cfgs


def skeleton(typ, S):
    sch = S[typ]
    lines = ["---", "type: " + typ, "version: 1", "author: <your role id>", "status: draft"]
    for k in sch.get("extra_front", []):
        hint = " | ".join(sch["enums"][k]) if k in sch.get("enums", {}) else "<value>"
        lines.append("%s: %s" % (k, hint))
    lines.append("---")
    for h in sch["headings"]:
        lines += ["", "## " + h, "..."]
    notes = []
    if sch.get("claims"):
        notes.append("at least %d tagged claims ([FACT src=..], [ESTIMATE basis=..], [GUESS])" % sch.get("min_claims", 1))
    for p in sch.get("patterns", []):
        notes.append(p.get("msg", p["regex"]))
    if sch.get("min_words"):
        notes.append("at least %d words" % sch["min_words"])
    if sch.get("max_words"):
        notes.append("at most %d words" % sch["max_words"])
    return "\n".join(lines), notes


def render_role(a, agents, skills, cfgs, contract):
    S = cfgs["schemas"]
    parts = [a["body"], "", contract.strip()]
    types = []
    for w in a.get("writes", []):
        m = re.match(r"^\.venture/artifacts/([^/*]+)/", w)
        if m and m.group(1) not in types and m.group(1) in S:
            types.append(m.group(1))
    if types:
        parts += ["", "## Artifact skeletons you write"]
        for t in types:
            sk, notes = skeleton(t, S)
            parts += ["", "### " + t, "```markdown", sk, "```"]
            if notes:
                parts.append("Validator requires: " + "; ".join(notes) + ".")
    for s in a.get("skills", []):
        parts += ["", "## Skill: " + s, skills[s]["body"]]
    if a.get("optional_skills"):
        parts += ["", "## Optional skills", "Load with the Skill tool when useful: " + ", ".join("swarm:" + s for s in a["optional_skills"]) + "."]
    return "\n".join(parts) + "\n"


def roles_json(agents):
    keys = ("title", "dept", "reports_to", "tier", "stages", "tools", "reads", "writes", "max_instances")
    return {i: {k: a[k] for k in keys} for i, a in agents.items()}


WRITTEN = set()


def clean(d):
    d.mkdir(parents=True, exist_ok=True)


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    WRITTEN.add(path.resolve())


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    WRITTEN.add(dst.resolve())


def copy_tree(src, dst):
    for f in src.rglob("*"):
        if f.is_file():
            copy_file(f, dst / f.relative_to(src))


def copy_payload(dest, agents, cfgs):
    copy_file(CORE / "runtime" / "swarm.py", dest / "runtime" / "swarm.py")
    for n in ("roster", "limits", "models", "stages", "schemas"):
        copy_file(CORE / "config" / (n + ".json"), dest / "data" / (n + ".json"))
    put(dest / "data" / "roles.json", json.dumps(roles_json(agents), indent=2))


def build_claude(agents, skills, cfgs, contract):
    d = OUT / "claude"
    clean(d)
    tiers = cfgs["models"]["tiers"]
    over = cfgs["models"].get("role_overrides", {})
    for i, a in agents.items():
        tools = []
        for t in a["tools"]:
            tools += TOOLMAP[t]
        tools.append("Skill")
        model = over.get(i) or tiers[a["tier"]]
        fm = "---\nname: %s\ndescription: %s\ntools: %s\nmodel: %s\n---\n\n" % (i, json.dumps(a["description"]), ", ".join(dict.fromkeys(tools)), model)
        put(d / "agents" / (i + ".md"), fm + render_role(a, agents, skills, cfgs, contract))
    for n, s in skills.items():
        put(d / "skills" / n / "SKILL.md", "---\nname: %s\ndescription: %s\n---\n\n%s\n" % (n, json.dumps(s["description"]), s["body"]))
    o = agents["orchestrator"]
    put(d / "skills" / "orchestrate" / "SKILL.md", "---\nname: orchestrate\ndescription: \"Run the swarm as orchestrator: dispatch roles, enforce gates, keep the plan. Use after /swarm:run.\"\n---\n\n%s\n" % o["body"])
    copy_tree(SRC / "claude" / "commands", d / "commands")
    copy_tree(SRC / "claude" / "hooks", d / "hooks")
    put(d / ".claude-plugin" / "plugin.json", (SRC / "claude" / "plugin" / "plugin.json").read_text(encoding="utf-8"))
    copy_file(SRC / "claude" / "README.md", d / "README.md")
    copy_file(ROOT / "LICENSE", d / "LICENSE")
    copy_payload(d, agents, cfgs)


LITE = """# Swarm (sequential mode)

This host cannot spawn isolated subagents or run enforcement hooks, so the swarm runs one role at a time. PLUGIN_DIR is the folder that contains this plugin's `skills/`, `roles/`, `runtime/` and `data/` directories (two levels above this SKILL.md). RUNTIME is `PLUGIN_DIR/runtime/swarm.py`.

## One-shot
When the user gives you a problem, do not ask them to call anything by hand.
1. Mode: `god` if the user said god mode or told you never to ask, otherwise `guided`. Preset `lean` unless they asked for `full`.
2. Initialise (brief on stdin so quoting cannot break it):
```
python RUNTIME init --sequential --preset lean --mode <mode> --brief-file - <<'BRIEF'
<the brief, verbatim>
BRIEF
```
3. Run the pipeline below as the orchestrator. Guided mode: do the intake step, then stop only at gates. At a gate, show the human what the orchestrator section says, and when they reply `approve G1` (or `reject G1 <reason>`), run `python RUNTIME approve G1` (or `reject G1 <reason>`) for them. Only run it after the human's message. God mode: at a gate run `python RUNTIME autopilot G1` after writing the decisions section; it refuses and lists problems if anything is missing.

## Dispatching a role in this host
1. Write the task header (TASK, STAGE, INPUTS, OUTPUT) to `.venture/work/<task>/task.md`.
2. Start a fresh context if the host allows it (new chat, new session, or a background agent). Otherwise say "Now acting as <role>" and from then on use only `PLUGIN_DIR/roles/<role>.md` and the files listed under INPUTS. Do not use anything you remember from earlier roles.
3. Write only to that role's allowed paths. When its artifact is written, stop acting as the role.
4. After each artifact run `python RUNTIME validate`. For code run tests through `python RUNTIME ci --task <id> -- <command>`.
Isolation here is by convention, not enforced: there are no hooks, so test locking, path guards and budgets do not apply. Treat results as weaker evidence than a hook-enforced Claude Code run.

"""


def manifest_info():
    return json.loads((SRC / "claude" / "plugin" / "plugin.json").read_text(encoding="utf-8"))


def build_lite(host, agents, skills, cfgs, contract):
    d = OUT / host
    clean(d)
    info = manifest_info()
    for i, a in agents.items():
        put(d / "roles" / (i + ".md"), "# " + a["title"] + "\n\n" + a["description"] + "\n\n" + render_role(a, agents, skills, cfgs, contract))
    for n, s in skills.items():
        put(d / "skills" / n / "SKILL.md", "---\nname: %s\ndescription: %s\n---\n\n%s\n" % (n, json.dumps(s["description"]), s["body"]))
    idx = "\n".join("- `%s`: %s (stages: %s)" % (i, a["title"], ", ".join(a["stages"])) for i, a in agents.items() if i != "orchestrator")
    body = LITE + "## Roles\n" + idx + "\n\n" + agents["orchestrator"]["body"]
    desc = "Run a startup-style, evidence-gated pipeline on a problem: market research, PRD, design, threat model, cost, tested code, audit. Use when the user gives a business or product problem to take from idea to built MVP."
    put(d / "skills" / "swarm-run" / "SKILL.md", "---\nname: swarm-run\ndescription: %s\n---\n\n%s\n" % (json.dumps(desc), body))
    copy_payload(d, agents, cfgs)
    man = {k: info[k] for k in ("name", "displayName", "version", "description", "author", "homepage", "repository", "license", "keywords")}
    copy_file(ROOT / "LICENSE", d / "LICENSE")
    put(d / "README.md", "# Startup Swarm (%s, sequential mode)\n\nToken-intensive multi-agent startup pipeline. On this host a single agent plays each role in turn, so isolation is by convention, not enforced. Ask the agent to use the `swarm-run` skill with your problem. A run uses many tokens and can take hours; there is no cost benchmark yet. Not tested on a live %s host. Full documentation, security model and license (MIT): https://github.com/AnimeshShaw/startup-swarm\n" % (host.capitalize(), host.capitalize()))
    if host == "codex":
        man["skills"] = "./skills/"
        put(d / ".codex-plugin" / "plugin.json", json.dumps(man, indent=2) + "\n")
    else:
        put(d / ".cursor-plugin" / "plugin.json", json.dumps(man, indent=2) + "\n")


def build_root_manifests():
    info = manifest_info()
    put(ROOT / ".agents" / "plugins" / "marketplace.json", json.dumps({
        "name": "startup-swarm", "interface": {"displayName": "Startup Swarm"},
        "plugins": [{"name": info["name"], "source": {"source": "local", "path": "./adapters/codex"},
                     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}]}, indent=2) + "\n")
    put(ROOT / ".cursor-plugin" / "marketplace.json", json.dumps({
        "name": "startup-swarm", "owner": info["author"],
        "plugins": [{"name": info["name"], "source": "adapters/cursor", "description": info["description"]}]}, indent=2) + "\n")
    put(ROOT / ".claude-plugin" / "marketplace.json", json.dumps({
        "name": "startup-swarm", "owner": info["author"],
        "metadata": {"description": "Startup Swarm: token-intensive, evidence-gated multi-agent product pipeline.", "version": info["version"]},
        "plugins": [{"name": info["name"], "source": "./adapters/claude", "description": info["description"], "version": info["version"], "author": info["author"], "homepage": info["homepage"], "repository": info["repository"], "license": info["license"], "keywords": info["keywords"], "category": "development"}]}, indent=2) + "\n")


def build_docs(agents, skills, cfgs):
    S, R = cfgs["schemas"], cfgs["roster"]["presets"]
    lines = ["# Roles (generated by build.py; do not edit)", "",
             "Presets: " + "; ".join("`%s` = %d roles" % (k, len(v["roles"])) for k, v in R.items()), "",
             "| Role | Department | Reports to | Model tier | Stages | Lean | Full |", "|---|---|---|---|---|---|---|"]
    for i, a in agents.items():
        lines.append("| `%s` | %s | %s | %s | %s | %s | %s |" % (i, a["dept"], a["reports_to"], a["tier"], ", ".join(a["stages"]),
                     "yes" if i in R["lean"]["roles"] or i == "orchestrator" else "absorbed into `%s`" % R["lean"].get("absorb", {}).get(i, "-"),
                     "yes" if i in R["full"]["roles"] or i == "orchestrator" else "-"))
    lines += ["", "## What each role may read and write", ""]
    for i, a in agents.items():
        lines += ["### `%s`  %s" % (i, a["title"]), a["description"], "", "- tools: " + ", ".join(a["tools"]),
                  "- reads: " + ", ".join("`%s`" % x for x in a["reads"]), "- writes: " + (", ".join("`%s`" % x for x in a["writes"]) or "nothing"), ""]
    put(ROOT / "docs" / "roles.md", "\n".join(lines) + "\n")
    lines = ["# Artifacts (generated by build.py; do not edit)", "",
             "Every artifact is a Markdown file in `.venture/artifacts/<type>/` with front matter. `status: draft` skips structure checks; `status: final` is validated and is what gates look at.", ""]
    for t, sch in ((k, v) for k, v in S.items() if isinstance(v, dict)):
        sk, notes = skeleton(t, S)
        lines += ["## " + t, "", "Headings: " + ", ".join("`%s`" % h for h in sch["headings"]), ""]
        if notes:
            lines += ["Requirements: " + "; ".join(notes) + ".", ""]
    gates = cfgs["stages"]["gates"]
    lines += ["## Which artifacts each gate needs", ""]
    for g, gd in gates.items():
        lines.append("- **%s**: %s" % (g, ", ".join(a["type"] + (" (gate %s)" % a["gate"] if a.get("gate") else "") for a in gd["artifacts"])))
    put(ROOT / "docs" / "artifacts.md", "\n".join(lines) + "\n")


def main():
    agents, skills, cfgs = load_all()
    contract = (CORE / "protocol" / "CONTRACT.md").read_text(encoding="utf-8")
    build_claude(agents, skills, cfgs, contract)
    build_lite("codex", agents, skills, cfgs, contract)
    build_lite("cursor", agents, skills, cfgs, contract)
    build_root_manifests()
    build_docs(agents, skills, cfgs)
    print("built: %d roles, %d skills -> adapters/claude, adapters/codex, adapters/cursor, docs/roles.md, docs/artifacts.md" % (len(agents), len(skills)))
    stale = [f for h in ("claude", "codex", "cursor") for f in (OUT / h).rglob("*") if f.is_file() and f.resolve() not in WRITTEN and "__pycache__" not in f.parts]
    for f in stale:
        print("stale (no longer generated, delete by hand):", f.relative_to(ROOT))


if __name__ == "__main__":
    main()
