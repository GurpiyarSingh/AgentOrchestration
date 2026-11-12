---
name: test-design
description: Systematic unit-test design. Use when writing or reviewing tests to choose cases with equivalence classes, boundary values and error paths.
---

# Test design

For every function under test, derive cases instead of guessing:

1. **Equivalence classes:** split inputs into groups that should behave the same (valid, empty, invalid type, out of range). Write one test per class.
2. **Boundaries:** for every limit, test *exactly at* the limit, *one below* and *one above* (lengths, counts, numeric ranges, indexes).
3. **Error paths:** every documented exception or error return gets its own test (`pytest.raises` / `assert.throws`), including the message when the spec defines it.
4. **Recompute expectations by hand:** count characters, do the arithmetic, and trace the algorithm for each expected value before writing it. A wrong expectation is worse than no test.
5. **One behaviour per test:** name tests after the behaviour (`test_truncates_on_word_boundary`), not the input.
6. **Deterministic:** no network, clock, randomness or sleeps.

Before finishing, map every acceptance criterion to at least one test.
