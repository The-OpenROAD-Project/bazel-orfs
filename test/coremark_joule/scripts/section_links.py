#!/usr/bin/env python3
"""Turn every `§N.M` in the paper into a link to its heading, and check them.

GitHub derives a heading's anchor from its text: lowercased, punctuation
other than hyphens and spaces removed, spaces to hyphens. A reference
written as bare `§4.8` is a number the reader has to scroll for; written
as `[§4.8](#48-cross-checks-...)` it is a click, and it is also checkable
-- a heading that moves or is renumbered leaves a dangling anchor, which
is what the test over this module asserts against.

Two modes on the README: `--fix` rewrites the file, relinking every
reference (stale anchors included) from the current headings; without
it the module only reports. Lines inside fenced code blocks are left
alone.
"""

import argparse
import re
import sys

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
REF = re.compile(r"\[?§(\d+(?:\.\d+)?)(?:\]\(#[^)]*\))?")
SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)?)\.?\s")


def anchor(text):
    """GitHub's heading anchor for `text`."""
    t = text.strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def headings(lines):
    """{section number: anchor} for every numbered heading outside code."""
    out = {}
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADING.match(line)
        if not m:
            continue
        n = SECTION_NUMBER.match(m.group(2))
        if n:
            out[n.group(1)] = anchor(m.group(2))
    return out


def relink(text):
    """Return (new_text, dangling): every § reference linked to its heading."""
    lines = text.split("\n")
    table = headings(lines)
    dangling = []
    out = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code or line.startswith("    "):
            out.append(line)
            continue

        def sub(m):
            num = m.group(1)
            if num not in table:
                dangling.append(num)
                return "§" + num
            return "[§{}](#{})".format(num, table[num])

        out.append(REF.sub(sub, line))
    return "\n".join(out), sorted(set(dangling))


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("readme")
    p.add_argument("--fix", action="store_true", help="rewrite the file")
    args = p.parse_args(argv[1:])
    with open(args.readme) as f:
        text = f.read()
    new, dangling = relink(text)
    for d in dangling:
        print("section_links: §{} has no heading".format(d), file=sys.stderr)
    if args.fix:
        if new != text:
            with open(args.readme, "w") as f:
                f.write(new)
            print("section_links: rewrote {}".format(args.readme))
    elif new != text:
        print(
            "section_links: {} has unlinked or stale § references; run with --fix".format(
                args.readme
            ),
            file=sys.stderr,
        )
        return 1
    return 1 if dangling else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
