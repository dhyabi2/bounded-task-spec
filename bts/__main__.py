"""bts command line: validate, hash, evaluate a bounded task.

  bts validate <task.json>                      exit 0 valid, 1 invalid, 2 unreadable
  bts hash <file.json>                          sha256 of the file's canonical JSON
  bts spec-hash                                 sha256 of the pinned schema
  bts evaluate <task.json> <status> <evidence.json> [--at YYYY-MM-DDTHH:MM:SSZ]
                                                prints PASS / FAIL / UNKNOWN / PASS_SUPERSET;
                                                exit 0 PASS, 1 FAIL, 3 UNKNOWN, 4 PASS_SUPERSET
"""
import sys

import bts


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if args else 2
    cmd, rest = args[0], args[1:]
    try:
        if cmd == "validate" and len(rest) == 1:
            errors = bts.validate(bts.load(rest[0]))
            for e in errors:
                print(e)
            print("valid" if not errors else f"invalid ({len(errors)} error{'s' if len(errors) != 1 else ''})")
            return 0 if not errors else 1
        if cmd == "hash" and len(rest) == 1:
            print(bts.sha256_of(bts.load(rest[0])))
            return 0
        if cmd == "spec-hash" and not rest:
            print(bts.spec_hash())
            return 0
        if cmd == "evaluate" and len(rest) in (3, 5):
            at = None
            if len(rest) == 5:
                if rest[3] != "--at":
                    raise bts.BTSError("expected --at")
                at = bts.parse_deadline(rest[4])
            verdict, reasons = bts.evaluate(bts.load(rest[0]), int(rest[1]), bts.load_evidence(rest[2]), at)
            print(verdict)
            for r in reasons:
                print(f"  {r}")
            return {bts.PASS: 0, bts.FAIL: 1, bts.UNKNOWN: 3, bts.PASS_SUPERSET: 4}[verdict]
    except (bts.BTSError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
