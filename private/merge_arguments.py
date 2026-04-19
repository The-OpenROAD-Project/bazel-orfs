"""Merge .json argument files into a Makefile-style config."""

import json
import sys


def main():
    output_path = sys.argv[1]
    json_paths = sys.argv[2:]

    result = {}
    for path in json_paths:
        with open(path) as f:
            result.update(json.load(f))

    with open(output_path, "w") as out:
        for k, v in sorted(result.items()):
            out.write("export {}?={}\n".format(k, v))


if __name__ == "__main__":
    main()
