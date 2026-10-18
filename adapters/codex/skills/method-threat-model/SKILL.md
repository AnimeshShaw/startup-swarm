---
name: method-threat-model
description: "Threat modelling from the design: assets, boundaries, STRIDE threats, concrete mitigations. Use when writing or reviewing a threat model."
---

# Threat model

1. Assets: data, credentials, money paths, availability, reputation. Rank them.
2. Trust boundaries: where data crosses between users, services, third parties, and the browser. Draw them in words.
3. Threats: apply STRIDE per boundary. Number them T-1, T-2, ... with attacker, entry point, impact.
4. For products using LLMs add: prompt injection via any untrusted text, tool or agent abuse, data leakage across tenants, over-permissioned tool credentials, unsafe output handling.
5. Supply chain: dependency count, install scripts, pinned versions, CI secrets.
6. Mitigations must name a control and where it lives ("rate limit on /login in gateway", not "add security").
7. Residual risk: what remains after mitigations, in plain words. Each threat maps to at least one test the QA role can write, or says why not.
