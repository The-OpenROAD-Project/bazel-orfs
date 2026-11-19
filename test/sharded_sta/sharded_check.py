"""A sharded timing against the flat one.

    sharded_check.py <merged files...> -- <flat.ends>

Every flat endpoint is reported by exactly one shard (the merge refuses a
pin reported twice, and the counts agree); every exact endpoint has the
flat slack; and some endpoints are modelled, so the exact flag can fail.
"""

import json
import sys

import ends


def main(argv):
    i = argv.index("--")
    merged, flat_path = argv[:i], argv[i + 1]
    (report_path,) = [p for p in merged if p.endswith(".json")]
    (ends_path,) = [p for p in merged if p.endswith(".ends")]
    with open(report_path) as f:
        report = json.load(f)
    flat = ends.read_ends(flat_path)
    exact = ends.read_ends(ends_path)
    errors = []
    if report["endpoints"] != len(flat):
        errors.append(
            "%d endpoints reported, %d timed flat" % (report["endpoints"], len(flat))
        )
    if report["exact"] != len(exact):
        errors.append(
            "%d exact in the report, %d in the ends file"
            % (report["exact"], len(exact))
        )
    if not report["modelled"]:
        errors.append("no endpoint is modelled: the timing models are on no path")
    if not exact:
        errors.append("no endpoint is exact")
    errors += ends.compare(exact, flat, 0.001)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
