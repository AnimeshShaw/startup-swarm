---
name: method-test-first
description: "Tests written before code, traced to acceptance criteria, with abuse cases. Use when writing tests or a test plan."
---

# Test first

1. List the sprint's acceptance criteria ids. Every one gets at least one automated test, named after the id.
2. Cover the happy path, boundaries, invalid input and permission failures. For anything touching auth, money, files or external input add abuse cases from the threat model (T-n).
3. Run the tests before any code exists; record which fail and why. A test that passes on an empty implementation is broken.
4. Keep tests deterministic: fixed clocks, seeded randomness, no live network. Mock external services at the boundary.
5. `test-plan` has a traceability table (AC id to test names) and the full list of tests.
6. Once locked, the tests only change through a recorded dispute and your ruling.
