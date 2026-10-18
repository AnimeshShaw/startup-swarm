---
name: dept-compliance
description: "Compliance playbook: map target market and data to regimes and obligations. Use when writing a compliance map."
---

# Compliance playbook

1. Fix the target market(s), customer type (consumer, business, regulated) and data types (personal, health, payment, children's).
2. Candidate regimes, to be checked against primary sources: GDPR and UK GDPR; India DPDP Act 2023; CCPA/CPRA and other US state laws; HIPAA when US health data is handled for covered entities; PCI DSS when card data touches your systems; SOC 2 and ISO 27001 as customer-driven assurance; EU AI Act for AI features; accessibility rules such as WCAG; sector rules where relevant.
3. For each applicable regime: why it applies, the obligation as a product requirement (consent flow, data export, breach notice, retention limit, subprocessor list), and where in the design it is met.
4. Gaps: obligations the current design does not meet, with severity.
Cite the regulator's or standard body's own text; if you could not, tag GUESS. Mark the document as needing human legal review.
