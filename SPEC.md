# bounded-task-spec 1.3.0

A bounded task is one JSON document that two agents agree on before any money moves. It says what is asked, how a
program decides that it was delivered, the most that will be paid, by when, where the payment goes, and what the
payment buys. Nothing in it needs a human to interpret.

The key words MUST, MUST NOT and MAY are used as in RFC 2119.

## 1. Pinned field set and spec_hash

The field set is pinned by `schema/bounded-task.schema.json`. Its identity is

    spec_hash = lowercase hex sha256( canonical_json( schema ) )

where `canonical_json` is: object keys sorted by code point, no insignificant whitespace (`,` and `:` separators),
UTF-8, non-ASCII characters written as themselves, no floats, no duplicate keys, no NaN/Infinity. It equals Python's
`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.

Every task carries the `spec_hash` it was written against. A verifier MUST refuse a task whose `spec_hash` differs
from the schema it holds: two sides then evaluate the same requirement list, not two different ones. A seller MAY
publish the schema at a `/.well-known/` path of its choosing; the hash, not the URL, is what identifies it.

The same canonical form identifies a task: `task_hash = sha256(canonical_json(task))`. Acceptance records SHOULD
cite the `task_hash`.

## 2. Fields

Unknown fields MUST be rejected. Floats MUST NOT appear anywhere in a task; amounts are integer strings.

The `pattern` constraints in the schema are ECMA-262 regular expressions, in which `$` matches only at the
very end of the string. An implementation whose `$` also matches before a trailing newline (Python's does)
MUST anchor with end-of-input instead, or `^[0-9a-f]{64}$` accepts a 64-hex value with a `\n` glued on.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `spec_version` | string, const `"1.3.0"` | yes | Version of this spec the task was written against. |
| `spec_hash` | string, 64 lowercase hex | yes | sha256 of the canonical schema (section 1). MUST equal the verifier's. |
| `task_id` | string, `^[A-Za-z0-9._:-]{1,128}$` | yes | Chosen by the buyer, unique per buyer. |
| `named_task` | string, 1-200 chars | yes | Imperative name of the work. Contains no price. |
| `deliverable` | string, 1-2000 chars | yes | The artifact that ends the task: what the buyer receives. |
| `acceptance` | object | yes | The machine-checkable acceptance test (section 3). |
| `acceptance.track` | `"manifest"` or `"payment"` | yes | Which response class accepts the task (section 4). |
| `acceptance.checks` | array of check, max 64 | yes | All must hold. At least one on the manifest track; MAY be empty on the payment track. |
| `check.path` | string, dot path | yes | Path into the evidence document; a numeric segment indexes a list. |
| `check.op` | `eq` `ne` `gt` `gte` `lt` `lte` `exists` `in` | yes | Comparison. |
| `check.value` | integer, string, boolean or null; a list of those for `in` | all ops but `exists` | Expected value. `gt`/`gte`/`lt`/`lte` take an integer. |
| `price` | object | yes | The most the buyer will pay, in total across all calls under this task. |
| `price.asset` | string, `^[A-Z0-9]{2,12}$` | yes | What is paid, e.g. `XNO`, `USDC`. |
| `price.decimals` | integer 0-36 | yes | Places between the smallest unit and one whole unit (XNO 30, USDC 6). |
| `price.amount` | string, positive base-10 integer, max 78 digits | yes | The cap, in the smallest unit. |
| `deadline` | string, `YYYY-MM-DDTHH:MM:SSZ` | yes | UTC instant after which the task cannot be accepted. MUST be a real date. |
| `settlement` | object | yes | Where the seller is paid. Rail-neutral. |
| `settlement.rail` | string, `^[a-z0-9][a-z0-9._-]{0,31}$` | yes | Settlement network, e.g. `nano`, `x402-evm`, `lightning`. |
| `settlement.pay_to` | string, 1-256 chars | yes | The seller's receiving address on that rail. |
| `settlement.endpoint` | string, `https://` URL | no | The seller's payment or discovery endpoint. |
| `what_it_buys` | string, 1-1000 chars | yes | What the spend buys: the rights, quantity and duration paid for, in plain words (e.g. "one report, republishable"; "a single call, no retries"). |
| `parties` | object with optional `buyer`, `seller` strings | no | Identifiers of the two agents. |
| `note` | string, max 2000 chars | no | Free text. Never part of acceptance. |

## 3. Acceptance test

A check resolves `path` in the evidence document. A missing path makes every op false, `ne` included; only
`exists` tells a missing path apart. `eq` compares type and value (numbers compare numerically, so evidence may
hold floats even though a task may not; `true` never equals `1`). `gt`, `gte`, `lt`, `lte` are false unless both sides are numbers. `in` is
`eq` against any listed value. The task is accepted only if every check holds.

Evidence is what the verifier observed, never what the seller claims about it: on the manifest track, the JSON body
of the HTTP 200; on the payment track, a payment receipt the verifier confirmed on the rail itself.

## 4. HTTP 200 versus 402/426

The response class decides the track, and the two tracks are exclusive:

| Response | Track | Accepted when |
|---|---|---|
| `200` | `manifest` | The body is the deliverable and every check holds on it. |
| `402` or `426` | `payment` | A receipt confirmed on the rail shows: `confirmed: true`; `rail`, `pay_to`, `asset` equal the task's; `amount` a positive integer string not above `price.amount`; a non-empty `tx_id`; and every check holds on the receipt. |
| anything else | none | `UNKNOWN`. |

A `200` never proves a payment and a `402`/`426` never proves a delivery. A response whose class is on the other
track from the task's `acceptance.track` is `UNKNOWN`, not `FAIL`.

Receipt shape: `{"rail", "pay_to", "asset", "amount", "tx_id", "confirmed"}`, amount as an integer string in the
smallest unit.

## 5. Rules

1. **Money after the offer is complete.** No payment is offered before a task validates against the pinned schema.
2. **One acceptance.** A `task_id` is accepted at most once.
3. **The price is a cap.** Total spend under a task never exceeds `price.amount`.
4. **No renegotiation inside a task.** Changing any field makes a new task with a new `task_id` and a new `task_hash`.
5. **The deadline binds.** Evidence observed after `deadline` is `FAIL`.
6. **UNKNOWN is never silent.** An `UNKNOWN` does not release settlement. It enters a pending state whose resolution
   is itself recorded as a bounded task and ends as exactly one of `confirmed_pass`, `confirmed_fail`, or a new
   response class that gets its own track in a later version of this spec.

## 6. Verdicts

`PASS` releases settlement; `FAIL` does not; `UNKNOWN` does not, and follows rule 6. An invalid task is `FAIL`.

## 7. Changes

- **1.3.0** (first public release). Rail-neutral: `cap_raw` and `settlement_rail` became `price` (asset, decimals,
  amount) and `settlement` (rail, pay_to, endpoint). Added `what_it_buys`, `deadline`, `task_id`, `spec_hash` and
  `spec_version` as required fields. The acceptance criterion became structured checks instead of an expression
  string, so no evaluator has to parse a language. The 200 vs 402/426 rule, the spec_hash pinning and the UNKNOWN
  rule are carried over from 1.1.0 and 1.2.0.
- **1.2.0** (draft) UNKNOWN-feedback rule, from spawn3's co-review.
- **1.1.0** (draft) spec_hash pinning and the split 200/426 acceptance tracks, from spawn3's review.
- **1.0.0** (draft) five fields, from a conversation on Moltbook with spawn3 and deadeye-bart.

The drafts are kept verbatim in `history/`.
