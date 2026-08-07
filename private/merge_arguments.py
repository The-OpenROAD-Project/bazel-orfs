import json
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Merge .json argument files into a Makefile-style config.")
    parser.add_argument("output_path", help="Path to write the args.mk file")
    parser.add_argument("--filter", help="Path to JSON file containing 'allowed' and 'known' variables", default=None)
    parser.add_argument("json_paths", nargs="+", help="Paths to the input .json files")
    args = parser.parse_args()

    result = {}
    for path in args.json_paths:
        with open(path) as f:
            result.update(json.load(f))

    if args.filter:
        with open(args.filter) as f:
            filter_data = json.load(f)
        allowed = set(filter_data.get("allowed", []))
        known = set(filter_data.get("known", []))
    else:
        allowed = set()
        known = set()

    with open(args.output_path, "w") as out:
        for k, v in sorted(result.items()):
            if args.filter:
                if k in known and k not in allowed:
                    continue
            out.write("export {}?={}\n".format(k, v))


if __name__ == "__main__":
    main()
