"""bts: reference validator for bounded-task-spec (stdlib only).

The pinned schema (schema/bounded-task.schema.json) is the single source of the field set: validate() interprets
that file directly, then applies the rules a JSON Schema cannot express (spec_hash, real calendar dates, check
values, no floats). evaluate() applies the acceptance test and the HTTP 200 vs 402/426 rule. Nothing here moves
money or touches a network.
"""
import datetime
import hashlib
import json
import os
import re

SPEC_VERSION = "1.3.0"
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "schema", "bounded-task.schema.json")
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
MANIFEST_STATUSES = frozenset({200})
PAYMENT_STATUSES = frozenset({402, 426})


class BTSError(ValueError):
    """A document that cannot be loaded or canonicalized."""


# ---------------------------------------------------------------- canonical JSON and hashing

def _reject_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise BTSError(f"duplicate key: {key!r}")
        out[key] = value
    return out


def _reject_float(text):
    raise BTSError(f"floats are not allowed (found {text}); write amounts as integer strings")


def _reject_constant(text):
    raise BTSError(f"non-standard JSON constant: {text}")


def loads(text):
    """Parse JSON strictly: no duplicate keys, no floats, no NaN/Infinity."""
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicates, parse_float=_reject_float,
                          parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise BTSError(f"not valid JSON: {exc}") from None


def load(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BTSError("not UTF-8") from None
    return loads(text)


def load_evidence(path):
    """Evidence (a seller's body or a receipt) may hold floats; duplicate keys are still refused."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BTSError(f"evidence is not valid UTF-8 JSON: {exc}") from None


def canonical(obj):
    """Canonical bytes: keys sorted, no whitespace, UTF-8, no floats."""
    def check(o):
        if isinstance(o, float):
            raise BTSError("floats cannot be canonicalized")
        if isinstance(o, dict):
            for k, v in o.items():
                if not isinstance(k, str):
                    raise BTSError("object keys must be strings")
                check(v)
        elif isinstance(o, list):
            for v in o:
                check(v)
    check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_of(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def load_schema(path=SCHEMA_PATH):
    return load(path)


def spec_hash(path=SCHEMA_PATH):
    """The spec's identity: sha256 of the schema's canonical JSON."""
    return sha256_of(load_schema(path))


# ---------------------------------------------------------------- validation

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


#: A bare ``$`` in a pattern, skipping escapes and character classes (where ``$`` is literal).
_BARE_DOLLAR = re.compile(r"\\.|\[(?:\\.|[^\]\\])*\]|(\$)", re.DOTALL)


def _ecma_pattern(pattern):
    """A JSON Schema ``pattern`` is an ECMA-262 regex, where ``$`` matches only at the very end.

    Python's ``$`` also matches just before a trailing newline, so ``^[0-9a-f]{64}$`` would
    accept a 64-hex string with a ``\n`` glued on. Translate a bare ``$`` to ``\Z``.
    """
    return _BARE_DOLLAR.sub(lambda m: r"\Z" if m.group(1) else m.group(0), pattern)


def _walk(node, value, where, errors):
    """Interpret the subset of JSON Schema the pinned schema uses."""
    if "const" in node and value != node["const"]:
        errors.append(f"{where}: must be {node['const']!r}")
        return
    if "enum" in node and value not in node["enum"]:
        errors.append(f"{where}: must be one of {node['enum']}")
        return
    kind = node.get("type")
    if kind and not _TYPES[kind](value):
        errors.append(f"{where}: must be {kind}")
        return
    if isinstance(value, str):
        if len(value) < node.get("minLength", 0):
            errors.append(f"{where}: must not be empty" if node.get("minLength") == 1 else f"{where}: too short")
        if "maxLength" in node and len(value) > node["maxLength"]:
            errors.append(f"{where}: longer than {node['maxLength']} characters")
        if "pattern" in node and not re.search(_ecma_pattern(node["pattern"]), value):
            errors.append(f"{where}: does not match {node['pattern']}")
    if kind == "integer":
        if "minimum" in node and value < node["minimum"]:
            errors.append(f"{where}: below {node['minimum']}")
        if "maximum" in node and value > node["maximum"]:
            errors.append(f"{where}: above {node['maximum']}")
    if isinstance(value, dict):
        props = node.get("properties", {})
        for name in node.get("required", []):
            if name not in value:
                errors.append(f"{where}.{name}: required")
        if node.get("additionalProperties") is False:
            for name in sorted(set(value) - set(props)):
                errors.append(f"{where}.{name}: unknown field")
        for name, sub in props.items():
            if name in value:
                _walk(sub, value[name], f"{where}.{name}", errors)
    if isinstance(value, list):
        if "maxItems" in node and len(value) > node["maxItems"]:
            errors.append(f"{where}: more than {node['maxItems']} items")
        if "items" in node:
            for i, item in enumerate(value):
                _walk(node["items"], item, f"{where}[{i}]", errors)


def _scalar(v):
    return v is None or isinstance(v, (str, bool, int))


def validate(task, schema=None):
    """Return a list of error strings; empty means valid."""
    schema = schema if schema is not None else load_schema()
    errors = []
    try:
        canonical(task)
    except BTSError as exc:
        return [f"$: {exc}"]
    _walk(schema, task, "$", errors)
    if not isinstance(task, dict):
        return errors
    if isinstance(task.get("spec_hash"), str) and re.fullmatch(r"[0-9a-f]{64}", task["spec_hash"]):
        expected = sha256_of(schema)
        if task["spec_hash"] != expected:
            errors.append(f"$.spec_hash: does not match the pinned schema ({expected})")
    deadline = task.get("deadline")
    if isinstance(deadline, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", deadline):
        try:
            parse_deadline(deadline)
        except ValueError:
            errors.append("$.deadline: not a real UTC date and time")
    checks = (task.get("acceptance") or {}).get("checks") if isinstance(task.get("acceptance"), dict) else None
    if isinstance(checks, list):
        for i, check in enumerate(checks):
            if not isinstance(check, dict) or "op" not in check:
                continue
            where = f"$.acceptance.checks[{i}]"
            op = check["op"]
            if op == "exists":
                if "value" in check:
                    errors.append(f"{where}.value: not allowed with exists")
            elif "value" not in check:
                errors.append(f"{where}.value: required for {op}")
            elif op == "in":
                if not isinstance(check["value"], list) or not all(_scalar(v) for v in check["value"]):
                    errors.append(f"{where}.value: must be a list of scalars for in")
            elif not _scalar(check["value"]):
                errors.append(f"{where}.value: must be a scalar")
            elif op in ("gt", "gte", "lt", "lte") and not _TYPES["integer"](check["value"]):
                errors.append(f"{where}.value: must be an integer for {op}")
    if (isinstance(task.get("acceptance"), dict) and task["acceptance"].get("track") == "manifest"
            and isinstance(checks, list) and not checks):
        errors.append("$.acceptance.checks: the manifest track needs at least one check")
    return errors


def parse_deadline(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


# ---------------------------------------------------------------- acceptance

_MISSING = object()


def _resolve(doc, path):
    cur = doc
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list) and seg.isdigit() and int(seg) < len(cur):
            cur = cur[int(seg)]
        else:
            return _MISSING
    return cur


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def run_check(check, doc):
    """True or False for one check against one evidence document."""
    got = _resolve(doc, check["path"])
    op = check["op"]
    if op == "exists":
        return got is not _MISSING
    if got is _MISSING:
        return False
    want = check.get("value")
    if op == "eq":
        return type(got) is type(want) and got == want or (_number(got) and _number(want) and got == want)
    if op == "ne":
        return not run_check({**check, "op": "eq"}, doc)
    if op == "in":
        return any(run_check({"path": check["path"], "op": "eq", "value": w}, doc) for w in want)
    if not (_number(got) and _number(want)):
        return False
    return {"gt": got > want, "gte": got >= want, "lt": got < want, "lte": got <= want}[op]


def classify(status):
    """The HTTP 200 vs 402/426 rule: which acceptance track a response class belongs to."""
    if status in MANIFEST_STATUSES:
        return "manifest"
    if status in PAYMENT_STATUSES:
        return "payment"
    return None


def _receipt_problems(task, receipt):
    if not isinstance(receipt, dict):
        return ["receipt is not an object"]
    s, p = task["settlement"], task["price"]
    out = []
    if receipt.get("confirmed") is not True:
        out.append("payment not confirmed")
    for key, want in (("rail", s["rail"]), ("pay_to", s["pay_to"]), ("asset", p["asset"])):
        if receipt.get(key) != want:
            out.append(f"receipt {key} does not match the task")
    tx = receipt.get("tx_id")
    if not isinstance(tx, str) or not tx:
        out.append("receipt has no tx_id")
    amount = receipt.get("amount")
    if not (isinstance(amount, str) and re.fullmatch(r"[1-9][0-9]{0,77}", amount)):
        out.append("receipt amount is not a positive integer string")
    elif int(amount) > int(p["amount"]):
        out.append("receipt amount exceeds the price cap")
    return out


def evaluate(task, status, evidence, observed_at=None):
    """Return (verdict, reasons). verdict is PASS, FAIL or UNKNOWN; UNKNOWN never releases settlement."""
    errors = validate(task)
    if errors:
        return FAIL, ["task is invalid"] + errors
    if observed_at is not None and observed_at > parse_deadline(task["deadline"]):
        return FAIL, ["evidence observed after the deadline"]
    track = classify(status)
    if track is None:
        return UNKNOWN, [f"HTTP {status} belongs to no acceptance track"]
    if track != task["acceptance"]["track"]:
        return UNKNOWN, [f"HTTP {status} is the {track} track; this task accepts on the {task['acceptance']['track']} track"]
    reasons = []
    if track == "payment":
        reasons += _receipt_problems(task, evidence)
    for i, check in enumerate(task["acceptance"]["checks"]):
        if not run_check(check, evidence):
            reasons.append(f"check {i} failed: {check['path']} {check['op']} {check.get('value', '')!r}".rstrip())
    return (FAIL, reasons) if reasons else (PASS, [])
