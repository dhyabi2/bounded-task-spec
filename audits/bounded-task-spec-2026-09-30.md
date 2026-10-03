# Audit 2026-09-30

First audit of this repository.

## Checked

- `python3 -m unittest discover -s tests`: 33 passed, 1 skipped before any change.
- Every `pattern` in `schema/bounded-task.schema.json` against `_walk`'s interpretation of it.
- `validate()`'s extra rules that a JSON Schema cannot express: `spec_hash`, real calendar dates,
  check values, no floats, no duplicate keys.
- `run_check` against the op table in SPEC.md §3, including `ne` on a missing path, `true` vs `1`,
  and int/float comparison. All match the spec.
- `_receipt_problems` against SPEC.md §4 and rule 3: the price is a cap, so an amount below
  `price.amount` is correctly accepted and one above is refused.
- `canonical`/`sha256_of` round trips, and that the examples carry the current `spec_hash`.

## Found and fixed

**An anchored `pattern` accepted a value with a newline glued on, which silently disabled the
`spec_hash` and deadline checks.** Python's `$` matches just before a trailing newline; the
ECMA-262 `$` that JSON Schema specifies does not. Every pattern in the pinned schema is `^...$`,
so `spec_hash = "<wrong 64 hex>\n"` satisfied `^[0-9a-f]{64}$` in `_walk` — and then
`validate()`'s own `re.fullmatch(r"[0-9a-f]{64}", ...)` guard failed, so the comparison against
the schema's real hash was **skipped entirely**. `validate()` returned `[]` for a task whose
`spec_hash` was wrong, defeating SPEC.md §1 ("A verifier MUST refuse a task whose `spec_hash`
differs from the schema it holds").

The same hole reached `deadline`: `"2026-02-31T00:00:00Z\n"` passed the pattern, skipped the
real-date check (guarded by the same `re.fullmatch` shape), validated clean, and then made
`evaluate()` raise an uncaught `ValueError` from `strptime`. `task_id`, `price.asset`,
`price.amount` and `settlement.rail` were bypassable the same way.

Fixed by translating a bare `$` in a pattern to `\Z` (`_ecma_pattern`), leaving `$` literal
inside a character class or after a backslash. One line at the call site in `_walk`; the schema
is unchanged, so `spec_hash` is unchanged. SPEC.md now names the regex dialect, since it never
said which one an implementation should use — that omission is what allowed the bug to look
correct. The repository's own law caught the resulting change to the published `SPEC.md` hash,
which is updated in the README.

## Not changed

- `_TYPES` covers only `object`, `array`, `string`, `integer`, `boolean`, and `_walk` would
  raise `KeyError` on any other `type`. The pinned schema uses only those four, so nothing is
  reachable today; a schema change would surface it.
- `_resolve` treats a path segment as a list index when `seg.isdigit()`, which is true for
  non-ASCII digits that `int()` then rejects. Unreachable: `check.path` is constrained to
  `^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$`.
