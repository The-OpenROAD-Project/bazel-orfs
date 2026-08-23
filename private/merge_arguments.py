import json
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="Merge .json argument files into a Makefile-style config."
    )
    parser.add_argument("output_path", help="Path to write the args.mk file")
    parser.add_argument(
        "--filter",
        help="Path to JSON file containing the 'drop' variable denylist",
        default=None,
    )
    parser.add_argument(
        "--include",
        "--mk-include",
        "--mk-includes",
        action="append",
        dest="mk_includes",
        help="Path to .mk file to include at the end",
        default=[],
    )
    parser.add_argument(
        "json_paths", nargs="*", help="Paths to the input .json files", default=[]
    )
    args = parser.parse_args()

    result = {}
    for path in args.json_paths:
        with open(path) as f:
            result.update(json.load(f))

    if args.filter:
        with open(args.filter) as f:
            drop = set(json.load(f).get("drop", []))
    else:
        drop = set()

    with open(args.output_path, "w") as out:
        # MORATORIUM(filter-decided-once): this is a denylist APPLIER, not a
        # keep/drop predicate. The decision is made once at analysis time by
        # dropped_variables() in private/stages.bzl and handed over as
        # {"drop": [...]}; re-deriving it here is what used to let the two
        # time domains drift apart. Variables absent from the denylist —
        # including every variable unknown to ORFS variables.yaml, which is
        # the escape hatch — are kept.
        # See the two-time-domains block in private/stages.bzl.
        for k, v in sorted(result.items()):
            if k in drop:
                continue
            out.write("export {}?={}\n".format(k, v))

        for inc in args.mk_includes:
            out.write("include {}\n".format(inc))


if __name__ == "__main__":
    main()
