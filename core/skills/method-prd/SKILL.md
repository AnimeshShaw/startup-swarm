---
name: method-prd
description: PRD with ruthless MVP scope and testable acceptance criteria. Use when writing a product requirements document.
---
# PRD

Sections: problem, users, scope, non-goals, requirements, acceptance criteria, risks.
- Problem and users cite the market brief; do not restate unverified claims as fact.
- Scope is the smallest build that tests the riskiest hypothesis. Everything else is a non-goal with a reason.
- Requirements are verbs a tester can check. Avoid "fast", "easy", "secure" unless given a number or a named control.
- Acceptance criteria use ids AC-1, AC-2, ... in the form "Given / When / Then", with a measurable result. Each requirement maps to at least one.
- Risks: top five, each with a mitigation or a test.
If a criterion cannot be automated, say how it will be verified by a human instead.
