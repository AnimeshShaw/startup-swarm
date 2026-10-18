---
name: method-blind-audit
description: Audit a change from spec, tests, diff and CI result only. Use when reviewing implementation work.
---
# Blind audit

Check in this order
1. CI: `ci.json` exists, is recent, `passed: true`, `tests_intact: true`. Otherwise reject.
2. Spec: does the diff implement the task's acceptance criteria, and only them? Unrequested features are findings.
3. Tests: do they actually prove the criteria, or would a hard-coded answer pass? Look for special-casing of test inputs.
4. Correctness: error paths, concurrency, idempotency, resource cleanup, off-by-one.
5. Security: untrusted input, authorisation on every path, secrets, injection, unsafe deserialisation, new dependencies.
6. Maintainability: only what will cause a real bug or a real cost later.

Write at least five concrete failure modes and say whether you found evidence of each. Findings cite file and line. Verdict is approve, reject or veto (veto is for security-critical flaws). If you cannot tell, reject and say what evidence would let you approve.
