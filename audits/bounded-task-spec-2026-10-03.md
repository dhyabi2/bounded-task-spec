# bounded-task-spec - audit 2026-10-03

Read before merging #1 (`pass-superset`, open since 2026-09-28). Nothing in this
repository moves money; what it does decide is whether a paid agent-to-agent task is
accepted, so the defect class that matters here is **a task accepted that should be
refused**, which is a payment released that should not have been.

## Checked

- `python3 -m unittest discover -s tests` on `main` (**38 tests, OK**) and on this branch
  merged with `main` (**51 tests, OK**). The branch's own body claimed 47; `main`'s #2
  added 4 after the branch was cut, which is the difference.
- The merge itself. It did **not** apply cleanly: `README.md` conflicted on the pinned-spec
  table, and - the part a "mergeable: clean" flag would not have caught - `SPEC.md`
  auto-merged to a text that is **neither side's**, because #2 added the ECMA-262 wording
  to it on `main`. The branch pinned `f948177c…` for `SPEC.md`; the merged file hashes to
  `3ba1c817a8b6a5fa37c5dc222dd901c7da67292f9576f083ee7b0a273b68a441`. Resolved by keeping
  1.4.0's version and `spec_hash` (the schema is untouched by #2, so
  `6ea18ba6…` still verifies) and recomputing the `SPEC.md` digest. The repository's own
  law at `tests/test_bts.py:54` compares the README's claim against the file and is what
  proves the resolution right - it fails on the branch's value and passes on the computed
  one.
- That #2's fix survived the merge rather than being reverted by the older branch:
  `_ecma_pattern` and its `\Z` rewrite are present at `bts/__init__.py:118-124` and still
  called from the pattern check at line 144.
- The `PASS_SUPERSET` path for the one thing that would make it dangerous - whether
  surplus can rescue a task that should fail. It cannot: `evaluate()` collects every
  reason first and `if reasons: return FAIL` (`bts/__init__.py:357-359`) runs **before** the
  surplus branch, so surplus is only reachable once every check held and every declared
  artifact arrived with its pinned bytes. `_artifact_problems` refuses a missing declared
  artifact, a pinned hash that differs, a name delivered twice, and a list that is absent
  or malformed. No amount is computed or changed anywhere on the new path; the price-cap
  check in `_receipt_problems` is untouched.
- What a consumer that has never heard of 1.4.0 does with the new verdict, since that is
  where a silent acceptance would come from. Both directions fail safe: a caller testing
  `verdict == PASS` sees `PASS_SUPERSET` and treats the task as not accepted, and a caller
  testing the CLI's exit status sees 4 rather than 0. SPEC.md section 6 states this
  requirement rather than leaving it to be inferred.

## Found

One archival inconsistency, recorded and **not** changed. `history/v1.3.0/SPEC.md` is the
1.3.0 text as published, hashing to `8e30984f…`, which is the value `main`'s README
carried before #2. #2 then edited `SPEC.md` while leaving the version at 1.3.0, so `main`
last claimed `186dfbd0…` for "1.3.0" while the archived copy is still the earlier text -
and the archived text is the one that is silent about which regex dialect a `pattern` is
written in, the ambiguity #2 existed to remove. Nobody paying or being paid is hurt by
this, and "verbatim 1.3.0" is a deliberate choice the branch states, so refreshing the
archive is a judgement for the maintainer rather than a defect to fix from here.

## Fixed

Nothing beyond the merge resolution above. The branch's own change is the content.

## Could not verify

- The `jsonschema` parity test ran (the package is importable here), but only against the
  one installed version; the branch's claim that the suite passes "with the stdlib only"
  was not re-checked in an environment without `jsonschema`.
- Nothing about settlement in practice: this repository has no rail and no node, so
  whether a `PASS_SUPERSET` quarantine is honoured by whatever releases XNO is outside
  what any test here can observe.
