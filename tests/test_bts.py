"""Laws for bounded-task-spec. Run: python3 -m unittest discover -s tests"""
import copy
import datetime
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
import bts  # noqa: E402

EX = os.path.join(ROOT, "examples")


def ex(*parts):
    return os.path.join(EX, *parts)


def cli(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "bin", "bts"), *args],
                          capture_output=True, text=True, cwd=ROOT)


class Canonical(unittest.TestCase):
    def test_key_order_and_whitespace_do_not_change_the_hash(self):
        a = bts.loads('{"b": 1, "a": {"y": "ü", "x": [1, 2]}}')
        b = bts.loads('{"a":{"x":[1,2],"y":"ü"},"b":1}')
        self.assertEqual(bts.sha256_of(a), bts.sha256_of(b))

    def test_canonical_form_is_the_documented_one(self):
        self.assertEqual(bts.canonical({"b": 1, "a": "é"}), '{"a":"é","b":1}'.encode("utf-8"))

    def test_floats_duplicates_and_constants_are_refused(self):
        for text in ('{"a": 1.5}', '{"a": 1, "a": 2}', '{"a": NaN}', '{"a": 1e3}'):
            with self.assertRaises(bts.BTSError, msg=text):
                bts.loads(text)

    def test_spec_hash_is_sha256_of_canonical_schema(self):
        schema = json.load(open(bts.SCHEMA_PATH))
        want = hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(bts.spec_hash(), want)

    def test_readme_publishes_the_current_spec_hash(self):
        readme = open(os.path.join(ROOT, "README.md")).read()
        self.assertIn(bts.spec_hash(), readme)

    def test_readme_publishes_the_current_spec_md_hash(self):
        readme = open(os.path.join(ROOT, "README.md")).read()
        digest = hashlib.sha256(open(os.path.join(ROOT, "SPEC.md"), "rb").read()).hexdigest()
        self.assertIn(digest, readme)


class SchemaParity(unittest.TestCase):
    def test_spec_md_documents_every_schema_field(self):
        schema, spec = bts.load_schema(), open(os.path.join(ROOT, "SPEC.md")).read()
        for name in schema["properties"]:
            self.assertIn(f"`{name}`", spec)
        self.assertIn("`what_it_buys`", spec)
        self.assertIn("what_it_buys", schema["required"])

    def test_version_agrees_everywhere(self):
        self.assertEqual(bts.load_schema()["properties"]["spec_version"]["const"], bts.SPEC_VERSION)
        self.assertTrue(open(os.path.join(ROOT, "SPEC.md")).read().startswith(f"# bounded-task-spec {bts.SPEC_VERSION}"))

    def test_examples_agree_with_the_real_jsonschema_library_when_installed(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed; the stdlib validator is the reference")
        schema = bts.load_schema()
        for path in glob.glob(ex("valid", "*.json")):
            jsonschema.validate(json.load(open(path)), schema)


class Validate(unittest.TestCase):
    def setUp(self):
        self.task = bts.load(ex("valid", "manifest-nano.json"))

    def test_valid_examples_are_valid(self):
        paths = glob.glob(ex("valid", "*.json"))
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            self.assertEqual(bts.validate(bts.load(path)), [], path)

    def test_invalid_examples_are_invalid(self):
        paths = glob.glob(ex("invalid", "*.json"))
        self.assertGreaterEqual(len(paths), 7)
        for path in paths:
            try:
                errors = bts.validate(bts.load(path))
            except bts.BTSError:
                continue
            self.assertTrue(errors, path)

    def test_every_required_field_is_required(self):
        for name in bts.load_schema()["required"]:
            t = copy.deepcopy(self.task)
            del t[name]
            self.assertIn(f"$.{name}: required", bts.validate(t))

    def test_unknown_fields_are_refused_at_every_level(self):
        for mutate in (lambda t: t.update(x=1), lambda t: t["price"].update(x=1),
                       lambda t: t["settlement"].update(x=1), lambda t: t["acceptance"].update(x=1),
                       lambda t: t["acceptance"]["checks"][0].update(x=1)):
            t = copy.deepcopy(self.task)
            mutate(t)
            self.assertTrue(any("unknown field" in e for e in bts.validate(t)))

    def test_spec_hash_must_match(self):
        t = dict(self.task, spec_hash="f" * 64)
        self.assertTrue(any("does not match the pinned schema" in e for e in bts.validate(t)))

    def test_amount_is_a_positive_integer_string(self):
        for bad in ("0", "01", "1.5", "-1", "1e9", 10, ""):
            t = copy.deepcopy(self.task)
            t["price"]["amount"] = bad
            self.assertTrue(bts.validate(t), bad)

    def test_float_anywhere_is_refused(self):
        t = copy.deepcopy(self.task)
        t["price"]["decimals"] = 30.0
        self.assertTrue(bts.validate(t))

    def test_deadline_must_be_a_real_utc_instant(self):
        for bad in ("2026-02-30T00:00:00Z", "2026-12-31 23:59:59Z", "2026-12-31T23:59:59+00:00", "tomorrow"):
            self.assertTrue(bts.validate(dict(self.task, deadline=bad)), bad)

    def test_rail_is_free_but_shaped(self):
        for ok in ("nano", "x402-evm", "lightning", "ach"):
            t = copy.deepcopy(self.task)
            t["settlement"]["rail"] = ok
            self.assertEqual(bts.validate(t), [], ok)
        t["settlement"]["rail"] = "Nano Mainnet"
        self.assertTrue(bts.validate(t))

    def test_check_values(self):
        cases = [({"path": "a", "op": "eq"}, "required"), ({"path": "a", "op": "exists", "value": 1}, "not allowed"),
                 ({"path": "a", "op": "in", "value": 1}, "list"), ({"path": "a", "op": "gt", "value": "1"}, "integer"),
                 ({"path": "a", "op": "eq", "value": {"x": 1}}, "scalar"), ({"path": "a..b", "op": "exists"}, "match")]
        for check, word in cases:
            t = copy.deepcopy(self.task)
            t["acceptance"]["checks"] = [check]
            self.assertTrue(any(word in e for e in bts.validate(t)), (check, bts.validate(t)))

    def test_manifest_track_needs_a_check(self):
        t = copy.deepcopy(self.task)
        t["acceptance"]["checks"] = []
        self.assertTrue(bts.validate(t))

    def test_non_object_documents(self):
        for doc in ([], "x", 1, None):
            self.assertTrue(bts.validate(doc))


class Evaluate(unittest.TestCase):
    def setUp(self):
        self.manifest = bts.load(ex("valid", "manifest-nano.json"))
        self.payment = bts.load(ex("valid", "payment-usdc.json"))
        self.report = bts.load_evidence(ex("evidence", "report-pass.json"))
        self.receipt = bts.load_evidence(ex("evidence", "receipt-usdc.json"))

    def test_classify_is_the_200_vs_402_426_rule(self):
        self.assertEqual(bts.classify(200), "manifest")
        self.assertEqual(bts.classify(402), "payment")
        self.assertEqual(bts.classify(426), "payment")
        for s in (201, 204, 301, 400, 401, 403, 404, 429, 500, 503):
            self.assertIsNone(bts.classify(s), s)

    def test_manifest_pass_and_fail(self):
        self.assertEqual(bts.evaluate(self.manifest, 200, self.report)[0], bts.PASS)
        bad = bts.load_evidence(ex("evidence", "report-fail.json"))
        self.assertEqual(bts.evaluate(self.manifest, 200, bad)[0], bts.FAIL)
        self.assertEqual(bts.evaluate(self.manifest, 200, {})[0], bts.FAIL)

    def test_other_track_or_unclassified_status_is_unknown_never_fail_or_pass(self):
        self.assertEqual(bts.evaluate(self.manifest, 402, self.report)[0], bts.UNKNOWN)
        self.assertEqual(bts.evaluate(self.payment, 200, self.receipt)[0], bts.UNKNOWN)
        for s in (204, 500, 302):
            self.assertEqual(bts.evaluate(self.manifest, s, self.report)[0], bts.UNKNOWN)

    def test_payment_receipt_rules(self):
        self.assertEqual(bts.evaluate(self.payment, 402, self.receipt)[0], bts.PASS)
        self.assertEqual(bts.evaluate(self.payment, 426, self.receipt)[0], bts.PASS)
        for key, value in (("confirmed", False), ("pay_to", "someone-else"), ("rail", "nano"), ("asset", "XNO"),
                           ("amount", "10001"), ("amount", "0"), ("amount", 10000), ("tx_id", "")):
            r = dict(self.receipt, **{key: value})
            self.assertEqual(bts.evaluate(self.payment, 402, r)[0], bts.FAIL, (key, value))
        r = dict(self.receipt)
        del r["confirmed"]
        self.assertEqual(bts.evaluate(self.payment, 402, r)[0], bts.FAIL)

    def test_deadline(self):
        after = datetime.datetime(2027, 1, 1, tzinfo=datetime.timezone.utc)
        before = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
        self.assertEqual(bts.evaluate(self.manifest, 200, self.report, after)[0], bts.FAIL)
        self.assertEqual(bts.evaluate(self.manifest, 200, self.report, before)[0], bts.PASS)

    def test_invalid_task_never_passes(self):
        t = dict(self.manifest, spec_hash="0" * 64)
        self.assertEqual(bts.evaluate(t, 200, self.report)[0], bts.FAIL)

    def test_ops(self):
        doc = {"a": 3, "b": "x", "c": True, "d": [10, 20], "f": 2.5, "n": None}
        truth = [("a", "eq", 3, True), ("a", "eq", "3", False), ("c", "eq", 1, False), ("c", "eq", True, True),
                 ("a", "ne", 4, True), ("a", "gt", 2, True), ("a", "gte", 3, True), ("a", "lt", 3, False),
                 ("a", "lte", 3, True), ("b", "gt", 1, False), ("f", "gt", 2, True), ("d.1", "eq", 20, True),
                 ("d.5", "exists", None, False), ("b", "in", ["x", "y"], True), ("b", "in", ["y"], False),
                 ("n", "eq", None, True), ("missing", "ne", 1, False), ("a", "exists", None, True)]
        for path, op, value, want in truth:
            check = {"path": path, "op": op} if op == "exists" else {"path": path, "op": op, "value": value}
            self.assertIs(bts.run_check(check, doc), want, (path, op, value))


class CLI(unittest.TestCase):
    def test_validate_exit_codes(self):
        self.assertEqual(cli("validate", ex("valid", "manifest-nano.json")).returncode, 0)
        self.assertEqual(cli("validate", ex("invalid", "wrong-spec-hash.json")).returncode, 1)
        self.assertEqual(cli("validate", ex("invalid", "float-amount.json")).returncode, 2)
        self.assertEqual(cli("validate", ex("valid", "nope.json")).returncode, 2)

    def test_hash_prints_the_canonical_sha256(self):
        out = cli("hash", "schema/bounded-task.schema.json")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.strip(), bts.spec_hash())
        self.assertRegex(cli("hash", ex("valid", "payment-usdc.json")).stdout.strip(), r"^[0-9a-f]{64}$")

    def test_evaluate_exit_codes(self):
        t = ex("valid", "manifest-nano.json")
        self.assertEqual(cli("evaluate", t, "200", ex("evidence", "report-pass.json")).returncode, 0)
        self.assertEqual(cli("evaluate", t, "200", ex("evidence", "report-fail.json")).returncode, 1)
        self.assertEqual(cli("evaluate", t, "426", ex("evidence", "report-pass.json")).returncode, 3)
        late = cli("evaluate", t, "200", ex("evidence", "report-pass.json"), "--at", "2027-01-01T00:00:00Z")
        self.assertEqual(late.returncode, 1)

    def test_module_entry_point(self):
        out = subprocess.run([sys.executable, "-m", "bts", "spec-hash"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.stdout.strip(), bts.spec_hash())


class Hygiene(unittest.TestCase):
    def test_examples_use_obvious_placeholders(self):
        for path in glob.glob(ex("*", "*.json")):
            text = open(path).read()
            for addr in re.findall(r'"pay_to": "([^"]+)"', text):
                self.assertIn("PLACEHOLDER", addr, path)
            for host in re.findall(r"https://([^/\"]+)", text):
                self.assertTrue(host.endswith(".example"), (path, host))

    def test_examples_carry_the_current_spec_hash(self):
        for path in glob.glob(ex("valid", "*.json")):
            self.assertEqual(bts.load(path)["spec_hash"], bts.spec_hash(), path)


class Artifacts(unittest.TestCase):
    """1.4.0: declared artifacts, the PASS_SUPERSET verdict and the surplus decision window (spawn3's predicate)."""

    def setUp(self):
        self.task = bts.load(ex("valid", "manifest-artifacts.json"))
        self.exact = bts.load_evidence(ex("evidence", "artifacts-exact.json"))
        self.superset = bts.load_evidence(ex("evidence", "artifacts-superset.json"))

    def test_exact_delivery_passes(self):
        self.assertEqual(bts.evaluate(self.task, 200, self.exact), (bts.PASS, []))

    def test_surplus_with_passing_predicate_is_pass_superset(self):
        verdict, reasons = bts.evaluate(self.task, 200, self.superset)
        self.assertEqual(verdict, bts.PASS_SUPERSET)
        self.assertTrue(any("extra.bin" in r and "quarantined" in r for r in reasons), reasons)
        self.assertTrue(any("72" in r and "discard" in r for r in reasons), reasons)

    def test_surplus_never_rescues_a_failing_predicate(self):
        bad = copy.deepcopy(self.superset)
        bad["report"]["tests_failed"] = 1
        self.assertEqual(bts.evaluate(self.task, 200, bad)[0], bts.FAIL)

    def test_missing_declared_artifact_fails(self):
        ev = copy.deepcopy(self.exact)
        ev["artifacts"] = [a for a in ev["artifacts"] if a["name"] != "report.json"]
        self.assertEqual(bts.evaluate(self.task, 200, ev)[0], bts.FAIL)

    def test_pinned_hash_must_match(self):
        ev = copy.deepcopy(self.exact)
        for a in ev["artifacts"]:
            if a["name"] == "schema.json":
                a["sha256"] = "0" * 64
        self.assertEqual(bts.evaluate(self.task, 200, ev)[0], bts.FAIL)

    def test_malformed_artifact_lists_fail(self):
        for artifacts in ("x", [{"name": "report.json"}], [{"name": "a", "sha256": "A" * 64}],
                          self.exact["artifacts"] + self.exact["artifacts"][:1]):
            ev = dict(self.exact, artifacts=artifacts)
            self.assertEqual(bts.evaluate(self.task, 200, ev)[0], bts.FAIL, artifacts)
        ev = dict(self.exact)
        del ev["artifacts"]
        self.assertEqual(bts.evaluate(self.task, 200, ev)[0], bts.FAIL)

    def test_other_track_is_still_unknown(self):
        self.assertEqual(bts.evaluate(self.task, 402, self.superset)[0], bts.UNKNOWN)

    def test_the_surplus_default_is_written_in_the_task(self):
        for key in ("decision_window_hours", "on_expiry"):
            t = copy.deepcopy(self.task)
            del t["acceptance"]["artifacts"]["surplus"][key]
            self.assertIn(f"$.acceptance.artifacts.surplus.{key}: required", bts.validate(t))
        t = copy.deepcopy(self.task)
        del t["acceptance"]["artifacts"]["surplus"]
        self.assertIn("$.acceptance.artifacts.surplus: required", bts.validate(t))
        for hours in (0, 8761, "72"):
            t = copy.deepcopy(self.task)
            t["acceptance"]["artifacts"]["surplus"]["decision_window_hours"] = hours
            self.assertTrue(bts.validate(t), hours)
        t["acceptance"]["artifacts"]["surplus"] = {"decision_window_hours": 72, "on_expiry": "keep"}
        self.assertTrue(bts.validate(t))

    def test_declared_list_rules(self):
        cases = ([], [{"name": "a"}, {"name": "a"}], [{"name": ""}], [{"name": "a", "sha256": "xyz"}],
                 [{"name": "a", "x": 1}])
        for declared in cases:
            t = copy.deepcopy(self.task)
            t["acceptance"]["artifacts"]["declared"] = declared
            self.assertTrue(bts.validate(t), declared)

    def test_artifacts_belong_to_the_manifest_track_only(self):
        self.assertTrue(bts.validate(bts.load(ex("invalid", "artifacts-on-payment-track.json"))))

    def test_cli_exit_code_for_pass_superset(self):
        t = ex("valid", "manifest-artifacts.json")
        out = cli("evaluate", t, "200", ex("evidence", "artifacts-superset.json"))
        self.assertEqual((out.returncode, out.stdout.splitlines()[0]), (4, "PASS_SUPERSET"))
        self.assertEqual(cli("evaluate", t, "200", ex("evidence", "artifacts-exact.json")).returncode, 0)

    def test_pass_superset_is_not_pass(self):
        self.assertNotEqual(bts.PASS_SUPERSET, bts.PASS)

    def test_the_1_3_0_spec_is_kept_verbatim(self):
        old = bts.load(os.path.join(ROOT, "history", "v1.3.0", "bounded-task.schema.json"))
        self.assertEqual(bts.sha256_of(old), "bfca60bb1e7e02ef9c107827104b22a5f77fe6cdb26fcd9cf5a03aacee3cebfe")
        digest = hashlib.sha256(open(os.path.join(ROOT, "history", "v1.3.0", "SPEC.md"), "rb").read()).hexdigest()
        self.assertEqual(digest, "8e30984fafbad5aad3a64246d693dda8f366b4c4d97a6ceed3f67e68dbda0040")


if __name__ == "__main__":
    unittest.main()
