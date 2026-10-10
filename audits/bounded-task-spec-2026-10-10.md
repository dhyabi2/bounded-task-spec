# bounded-task-spec — audit 2026-10-10

One lens: can an agent pay, or be paid, in XNO against this contract today without being hurt.
Nothing here moves money; what it decides is whether a paid task is accepted, so the defects that
matter are a task accepted that should be refused, an amount that comes out wrong, and a verifier
that stops working at all while a settlement is pending.

Base: `c795d45` (`Bring the trailing-newline example up to 1.4.0 so it guards the hole again (#5)`).
`python3 -m unittest discover -s tests` before any change: **60 tests, OK**.

## The two open items from 2026-10-05

That audit recorded two findings it did not fix. Both were re-checked first thing:

* **`examples/invalid/spec-hash-trailing-newline.json` stuck at `spec_version` 1.3.0** — **closed**
  by #5. The file now reads `1.4.0`, so the artefact that documents the most dangerous bug this
  repository has had is live again rather than being refused for the wrong reason first.
* **`canonical()` raising `UnicodeEncodeError` instead of `BTSError` on a lone surrogate** —
  **still open, and fixed in this PR.** See below. That audit judged it harmless because the CLI
  turns it into exit 2; the part that is not harmless is what a library caller sees, which is the
  reason it is being fixed rather than recorded a second time.

## Found and fixed (this PR)

**A task document the counterparty supplies can make `validate()` raise instead of return** —
`bts/__init__.py:87` (`canonical`), reached from `validate()` at line 181 and `evaluate()`
through it.

`json` accepts the escape `"\ud800"`, so `bts.loads('{"note": "\ud800"}')` succeeds and yields a
Python string holding an unpaired surrogate. UTF-8 cannot encode one, so the final
`.encode("utf-8")` raised:

```
>>> bts.validate(bts.loads('{"note": "\\ud800"}'))
UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 9: surrogates not allowed
```

`validate()`'s docstring is *"Return a list of error strings; empty means valid"*, and it wraps
its `canonical(task)` call in `except BTSError` (lines 180-183) **precisely so** that a document
with no canonical form comes back as an error list. `UnicodeEncodeError` is not a `BTSError`, so
it walked straight through that handler and out of the function, and out of `evaluate()` with it.
In a paid agent-to-agent task the task document is the *counterparty's*, so a verifier calling
`validate()` — the way this repository's own CLI does — aborted rather than recording a refusal.

The fix raises `BTSError` from that encode, which is the same refusal `canonical()` already makes
for a float ("floats cannot be canonicalized") and for a non-string key. It adds a refusal and
nothing else:

* every document that had a canonical form still has the same one, so **no hash moves**.
  `spec_hash()` is still `6ea18ba671119d9b2fe1f0cbfde4f26954e1050743fa307eaac81c2c580ee279` and
  still matches the README; `SPEC.md` and `schema/` are not touched.
* a document with no canonical form was already refused — by a traceback. It is now refused by a
  verdict.

One behaviour does change category, and it is worth stating plainly: `python3 -m bts validate` on
such a file used to exit **2** ("unreadable", because `UnicodeEncodeError` is a `ValueError` and
`bts/__main__.py:45` catches it) and now exits **1** ("invalid"), because `validate()` returns an
error list. Both are refusals, and 1 is the category a float already gets — the document parsed,
its *content* has no canonical form. `hash` still exits 2. Neither was ever 0.

**Evidence.** 5 new laws. With `tests/` kept and `bts/` alone reverted to `main`: **3 errors**, all
three `UnicodeEncodeError` —
`Canonical.test_an_unpaired_surrogate_is_refused_as_a_canonicalisation_failure`,
`ValidateCanonicalisationFailure.test_validate_returns_an_error_list_rather_than_raising` and
`...test_evaluate_returns_a_verdict_rather_than_raising`. With the fix: **65 tests, OK**.

Two of the five are controls that hold either way, and are in deliberately:

* `test_a_surrogate_pair_written_as_escapes_is_still_canonicalised` — a *paired* surrogate escape
  (`"😀"`) is an ordinary character, and must keep hashing exactly as before. This is
  what shows the guard refuses only what genuinely has no UTF-8 form, rather than all escapes.
* `test_the_cli_refuses_it_with_a_message_and_no_traceback` — passes before and after, which is
  the honest record of the 2026-10-05 judgement that the CLI was never the victim here.

Mutation-checked: narrowing the new `except UnicodeEncodeError` to `except (RuntimeError,)` puts
the suite back to the same **3 errors**. The tree was restored byte-for-byte afterwards and the
suite re-run.

## Checked and clean

* **The amount path at real XNO scale, re-measured.** A 39-digit raw cap through `validate()` and
  `_receipt_problems`: cap, cap−1 accepted and cap+1 refused, exactly. The comparison is `int`
  against `int` behind a `[1-9][0-9]{0,77}` gate, so `+1`, a leading zero, a trailing newline, a
  leading space, Arabic-Indic digits, `1e30` and `1.33e+38` are all refused before `int()` is
  reached. No float and no `Decimal` anywhere on the amount path.
* **`evaluate()`'s ordering.** `if reasons: return FAIL` still precedes the surplus branch, so a
  surplus cannot rescue a failing check or a missing declared artifact.
* **The non-string declared-artifact-name crash fixed on 2026-10-05 stays fixed** (#4): a `name`
  written as a list is reported as `must be string` and `evaluate()` returns `FAIL`.
* **Canonicalisation is still injective and order-independent.** Key order and whitespace do not
  reach the digest; floats, duplicate keys and `NaN`/`Infinity` are refused at parse time;
  `PYTHONHASHSEED` cannot reach the digest because keys are sorted.
* **Every README command runs as documented**, and the published `spec_hash` and `SPEC.md` digest
  both still match the files (two laws hold them).
* **No credential in the tree or in `git rev-list --all`.** Every `pay_to` in `examples/` is the
  literal `PLACEHOLDER`, and a test holds that.

## Found, NOT fixed

**A pre-existing `SyntaxWarning` on every import** — `bts/__init__.py:136`, a docstring containing
`\Z` and `\n` in a non-raw string: `SyntaxWarning: invalid escape sequence '\Z'`. It predates this
change (confirmed by compiling `main`'s copy with `-W error::SyntaxWarning`) and is cosmetic —
nothing behaves differently — but every agent that imports the library sees it on stderr. Left
alone here because it is a different concern from the one this branch fixes and touching a
docstring quoting would be noise in this diff.

## Could not verify

* **Anything about settlement in practice.** There is no rail and no node in this repository, so
  whether a `PASS`, a `PASS_SUPERSET` quarantine or a refusal is honoured by whatever actually
  releases XNO is outside what any test here can observe. No XNO moved.
* **The suite on the other interpreters the workflow runs.** Only CPython 3.13.16 and 3.11.17 are
  installed here, and 3.8 is the README's floor. Nothing found depends on a version difference —
  `UnicodeEncodeError.reason`/`.start` are present in every supported version — but the claim was
  not re-measured across all seven; CI runs them on this PR.
* **Whether `settlement.pay_to` is a well-formed address on any rail.** The schema is rail-neutral
  and constrains it only by length, so a task can pin a `nano_` string no node would accept. That
  is a deliberate gap in the spec, not a defect in the validator.
