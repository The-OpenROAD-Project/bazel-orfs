"""Top's timing models: one cell each, named after its module, with the
arcs its module's logic gives it.

    models_check.py <tree.json> <model.lib>...
"""

import json
import os
import re
import sys


def cells(text):
    return re.findall(r'^\s*cell\s*\(\s*"?([^")]+)"?\s*\)', text, re.M)


def main(argv):
    with open(argv[0]) as f:
        modules = json.load(f)["modules"]
    errors = []
    texts = {}
    for path in argv[1:]:
        name = os.path.basename(path)[: -len(".lib")]
        with open(path) as f:
            text = f.read()
        texts[name] = text
        want = [m for m in modules if m.split("$", 1)[0] == name]
        if cells(text) != want:
            errors.append("%s: cells %s, want %s" % (path, cells(text), want))
        if "setup_rising" not in text:
            errors.append("%s: no setup arc, though its inputs reach registers" % path)
    if "combinational" in texts.get("Mid", ""):
        errors.append("Mid.lib: a combinational arc, though Mid's output is a register")
    if "combinational" not in texts.get("Other", ""):
        errors.append("Other.lib: no combinational arc, though q = r + d")
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
