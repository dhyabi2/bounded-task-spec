# bounded-task-spec - audit 2026-10-05

One lens: can an agent pay, or be paid, in XNO against this contract today without
being hurt. Nothing in the repository moves money; what it decides is whether a paid
task is accepted, so the defects that matter are a task accepted that should be
refused, an amount that comes out wrong, and a verifier that stops working at all
while a settlement is pending.

## Checked

- `python3 -m unittest discover -s tests` on `main` at 248c45e before any change:
  **58 tests, OK** (56 before the two added here).
- Every command the README tells a reader to run, verbatim, plus the two exit-code
  lines the workflow runs: `hash`, `validate`, `spec-hash`, `evaluate`, `bin/bts
  validate`, an invalid task exiting 1 and an unreadable one exiting 2. All as
  documented. The published `spec_hash` `6ea18ba6…` and the published `SPEC.md`
  digest `3ba1c817…` both still match the files.
- The amount path at real XNO scale. A 39-digit raw cap (`133248290 * 10**30`, the
  whole supply) through `validate()` and `_receipt_problems`: cap, cap-1 and
  cap+1 are accepted, accepted and refused exactly, with no float and no `decimal`
  anywhere on the path - the comparison at `bts/__init__.py:301` is `int` against
  `int` after a `[1-9][0-9]{0,77}` gate, so nothing rounds. Leading `+`, a leading
  zero, a trailing newline, a leading space, Arabic-Indic digits, `1e30` and
  `1.3324829e+38` are all refused by that gate before `int()` ever sees them, which
  matters because `int("١٠")` would otherwise succeed.
- Canonicalisation, for a collision and for instability. `canonical()` is
  `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`: key order
  and whitespace do not reach the digest, floats and duplicate keys are refused at
  parse time, and the dump is injective (an escaped backslash keeps an escape
  sequence apart from the characters that spell it), so no two distinct task
  documents were found that hash alike and none hashed differently on a second run.
  `PYTHONHASHSEED` cannot reach it because the keys are sorted.
- A differential fuzz of `validate()` against the real `jsonschema` library: every
  leaf and container of all three valid examples replaced by each of ~25 hostile
  values, comparing "the reference validator says valid" against "jsonschema says
  valid". No case where the stdlib validator accepts a task that jsonschema refuses.
  The suite only ran that parity over the *valid* examples before.
- The same fuzz over the evidence side - the document the counterparty supplies -
  driving `evaluate()` at 200, 402, 426 and 500 with mutated receipts, reports and
  artifact lists. No uncaught exception and no wrong verdict.
- `_receipt_problems` and `_artifact_problems` against SPEC.md sections 3.1 and 4,
  and the ordering in `evaluate()` that the 2026-10-03 audit relied on: `if reasons:
  return FAIL` still precedes the surplus branch, so surplus cannot rescue a failing
  check or a missing declared artifact.
- The tree and the whole of `git rev-list --all` for a committed credential. Nothing:
  no key, no seed, no token. Every `pay_to` in `examples/` is a literal
  `PLACEHOLDER` string and a test holds that true.

## Found

**A task whose declared artifact name is not a string crashes the validator instead
of being reported invalid.** `bts/__init__.py:226` built `set(names)` out of
`[d.get("name") for d in declared if isinstance(d, dict)]`. A `name` written as a
list or an object is unhashable, so `set()` raised `TypeError: unhashable type:
'list'` straight out of `validate()` - a function whose contract is "return a list of
error strings" - and out of `evaluate()` with it. `bts/__main__.py:45` handles
`(BTSError, OSError, ValueError)`; a `TypeError` is none of those, so
`python3 -m bts validate task.json` printed a traceback with nothing on stdout, and a
verifier that wraps the call the way the repository's own CLI does would abort rather
than record a verdict. No money is released by it: the process exit happens to be 1,
which is also "invalid" and "FAIL". Fixed by letting only the names that have the
declared type take part in the uniqueness rule - a non-string name is already
reported by `_walk` as `$.acceptance.artifacts.declared[0].name: must be string`, so
the task stays invalid for the same reason it always should have been, and nothing
that was refused before is accepted now.

**`examples/invalid/spec-hash-trailing-newline.json:2` is still at
`"spec_version": "1.3.0"`.** Recorded, not fixed here. That example exists to
demonstrate the hole #2 closed, and its own note says so. The 1.4.0 release bumped
every other invalid example and missed this one, because it was added on the other
branch and merged afterwards - the merge-miss class the 2026-10-03 audit described.
Today the file is refused for `spec_version` first, so if `_ecma_pattern` were ever
reverted the file would still be reported invalid and
`test_invalid_examples_are_invalid` would still pass. Nobody paying is hurt - the
`PatternAnchors` tests cover the behaviour directly - but the artefact that documents
the most dangerous bug this repository has had is inert.

**`canonical()` raises `UnicodeEncodeError`, not `BTSError`, on a lone surrogate.**
Recorded, not fixed. `bts.loads('{"note": "\\ud800"}')` succeeds, and
`json.dumps(..., ensure_ascii=False).encode("utf-8")` at `bts/__init__.py:87` then
raises. `validate()` wraps that call in `except BTSError` at lines 180-183, so the
intent was clearly to turn a canonicalisation failure into an error list, and this
one slips past it. It is harmless at the CLI: `UnicodeEncodeError` is a `ValueError`,
so `bts/__main__.py:45` catches it and both `validate` and `hash` exit 2,
"unreadable", which is the right refusal. Only a library caller sees the difference.

## Fixed

The crash above, on `fix/declared-name-not-a-string`, with two tests that fail
without it: one that `validate()` returns the type error and `evaluate()` returns
`FAIL`, and one that the CLI writes nothing to stderr and exits 1. The schema is not
touched, so `spec_hash` is unchanged; `SPEC.md` is not touched either.

## Could not verify

- Anything about settlement in practice. There is no rail and no node here, so
  whether a `PASS`, a `PASS_SUPERSET` quarantine or a refusal is honoured by whatever
  actually releases XNO is outside what any test in this repository can observe.
- The suite on the other six interpreters the workflow runs. Only CPython 3.11.15 is
  installed here, and 3.8 is the README's floor; nothing found depends on a version
  difference, but the claim was not re-measured.
- `jsonschema` parity against more than the one installed version of that library.
- Whether `settlement.pay_to` is a well-formed address on any rail. The schema is
  rail-neutral and constrains it only by length, so a task can pin a `nano_` string
  that no node would accept; that is a deliberate gap in the spec rather than a
  defect in the validator, and detecting it would need rail-specific checksum code
  the repository does not claim to have.
