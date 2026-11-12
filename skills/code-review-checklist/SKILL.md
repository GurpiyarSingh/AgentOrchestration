---
name: code-review-checklist
description: Checklist for reviewing a change against its specification. Use when deciding whether code is correct and ready to merge.
---

# Code review checklist

Work through these in order and report concrete findings only.

1. **Spec coverage:** each acceptance criterion is implemented *and* tested. List any criterion without a test.
2. **Correctness:** edge cases (empty input, limits, None/null, unicode, negative numbers), off-by-one errors, integer/float issues, mutation of inputs.
3. **Errors:** invalid input raises the documented error with a useful message; no silently swallowed exceptions.
4. **Tests:** expectations are right (recompute them), assertions are specific, tests are independent and deterministic.
5. **Clarity:** names say what things are; functions do one thing; no dead code or debugging leftovers.
6. **Types & docs:** public functions are typed and documented.

Severity guide: **high** = wrong behaviour or a failing/incorrect test; **medium** = missing case or design problem that matters; **low** = style.
Approve only when there are no high or medium findings.
