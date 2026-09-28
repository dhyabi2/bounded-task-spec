# bounded-task-spec

A pinned, content-hashed contract template for paid agent-to-agent tasks, with a reference validator.

Two agents that want to trade work for money agree one small JSON document first: what is asked, a
machine-checkable acceptance test, the price (a cap), the deadline, where the seller is paid, and what the spend
buys. A program, not a person, decides whether the task was delivered. The schema is rail-neutral: Nano (XNO) is
one settlement option among others. Nothing in this repository moves money.

"Contracts get boring when there's a reference implementation." This is that implementation.

## The pinned spec

| | |
|---|---|
| Version | **1.4.0** |
| `spec_hash` (sha256 of the canonical JSON of `schema/bounded-task.schema.json`) | `6ea18ba671119d9b2fe1f0cbfde4f26954e1050743fa307eaac81c2c580ee279` |
| sha256 of `SPEC.md` | `f948177c7800aed6049eea400c004485c9527b57dcb514188fcf92e6d22cd6fa` |

Check it yourself, no install:

    python3 -m bts hash schema/bounded-task.schema.json

Every task carries this `spec_hash`; a verifier refuses a task written against a different field set.

## Files

- [`SPEC.md`](SPEC.md) - every field with its type and meaning, the canonical-JSON rule, the HTTP 200 vs 402/426
  rule, the UNKNOWN rule.
- [`schema/bounded-task.schema.json`](schema/bounded-task.schema.json) - JSON Schema (2020-12). It is the pinned field set.
- [`bts/`](bts) - reference validator, Python 3.8+, standard library only. Any JSON Schema library checks the
  shape; four rules need the reference validator: `spec_hash` equality, a real calendar deadline, check values
  that fit their op, and declared artifacts (manifest track only, unique names).
- [`examples/`](examples) - valid and invalid tasks and sample evidence. Every address in them is a placeholder;
  never send anything to it.
- [`history/`](history) - the 1.0.0, 1.1.0 and 1.2.0 drafts and the 1.3.0 release (`history/v1.3.0/`), verbatim.

## Use

    python3 -m bts validate examples/valid/manifest-nano.json      # exit 0 valid, 1 invalid, 2 unreadable
    python3 -m bts hash examples/valid/manifest-nano.json          # task_hash: sha256 of canonical JSON
    python3 -m bts spec-hash                                       # the pinned schema's hash
    python3 -m bts evaluate examples/valid/manifest-nano.json 200 examples/evidence/report-pass.json
                                                                   # PASS (0), FAIL (1), UNKNOWN (3)
                                                                   # or PASS_SUPERSET (4)

`bin/bts` is the same CLI as a script: `bin/bts validate <file>`.

## The 200 vs 402/426 rule, in one line

A 200 body is judged on the `manifest` track, a 402 or 426 on the `payment` track (a confirmed receipt to the
task's own address, asset and rail, not above the cap); anything else, or the other track, is `UNKNOWN`, and
`UNKNOWN` never releases payment.

## Over-delivery

A task can declare the artifacts it expects. If everything declared arrives, the checks hold, and something extra
came along too, the verdict is `PASS_SUPERSET`. The declared artifacts are paid for. The extras are quarantined
until the buyer ratifies or rejects them within the task's own decision window, and the task says whether they are
discarded or released if nobody decides (SPEC.md section 3.1).

## Tests

    python3 -m unittest discover -s tests

## Maintainers

Maintained by the team behind [getunstuck.space](https://getunstuck.space). The spec grew out of a public
conversation with agents on Moltbook; spawn3's reviews shaped 1.1.0, 1.2.0 and 1.4.0. Issues and pull requests welcome.

License: MIT.
