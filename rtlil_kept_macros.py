#!/usr/bin/env python3
"""Validate the user-supplied kept_macros dict against the canonical RTLIL.

Walks the module hierarchy in 1_1_yosys_canonicalize.rtlil, for each
kept module collects the macro instances reachable from it (DFS through
non-kept descendants, stopping at descendant kept modules — those are
owned by their own partition). Compares to the user-declared dict.

Exit codes:
  0  user dict matches the derived dict — emits validated_kept_macros.json
  1  mismatch — prints the corrected dict on stderr (paste-ready), no output file

Slang elaborates parameterised instances to names like
'Base$Path.with.dots' — kept-module entries and macro entries reference
the *base* name (before any '$').

Usage: rtlil_kept_macros.py --rtlil <file> --kept-modules <json> \\
                            --macros <json> --user-kept-macros <json> \\
                            --top <name> --output <json>
"""
import argparse
import json
import re
import sys


def _base(name):
    """Base module name (strip slang '$path' suffix)."""
    return name.split("$", 1)[0]


def parse_rtlil(path):
    """Stream the RTLIL. Return:
       - modules: dict of full_name -> list of (cell_type_full, inst_name)
       - top: the module marked with `attribute \\top 1` (or None)

    Yosys built-in cells (types starting with '$') are skipped — they
    are logical primitives, never user modules or macros.
    """
    modules = {}
    top = None
    cur = None
    saw_top_attr = False
    module_re = re.compile(r"^module \\(\S+)")
    cell_re = re.compile(r"^  cell \\(\S+) \\(\S+)")
    with open(path) as f:
        for line in f:
            if line.startswith("attribute \\top 1"):
                saw_top_attr = True
                continue
            m = module_re.match(line)
            if m:
                cur = m.group(1)
                modules[cur] = []
                if saw_top_attr:
                    top = cur
                saw_top_attr = False
                continue
            # Module-end at column 0.
            if cur is not None and line == "end\n":
                cur = None
                continue
            saw_top_attr = False
            if cur is None:
                continue
            cm = cell_re.match(line)
            if cm:
                cell_type, inst = cm.group(1), cm.group(2)
                modules[cur].append((cell_type, inst))
    return modules, top


def build_base_to_full(modules):
    """Map base name -> list of full RTLIL module names sharing that base."""
    by_base = {}
    for full in modules:
        by_base.setdefault(_base(full), []).append(full)
    return by_base


def collect_macros_under(start_full, modules, by_base, kept_bases, macro_bases):
    """DFS from start_full, return set of macro base names instantiated
    in its subtree. Stop the walk at any descendant whose base is in
    kept_bases (those macros are owned by their own partition)."""
    found = set()
    visited = set()
    stack = [start_full]
    while stack:
        cur = stack.pop()
        if cur in visited:
            continue
        visited.add(cur)
        for cell_type_full, _inst in modules.get(cur, []):
            cell_base = _base(cell_type_full)
            if cell_base in macro_bases:
                found.add(cell_base)
                # Macros are blackboxes — no body to recurse into.
                continue
            if cell_base in kept_bases:
                # Descendant kept module owns its own partition.
                continue
            # Non-macro non-kept submodule: recurse.
            for full in by_base.get(cell_base, []):
                if full not in visited:
                    stack.append(full)
    return found


def derive_kept_macros(modules, top, kept_modules, macros):
    """Return dict: kept_module_name -> sorted list of macro names it uses.
    The synthetic key '_top' represents the residue — macros instantiated
    above any kept module in the hierarchy."""
    kept_bases = set(kept_modules)
    macro_bases = set(macros)
    by_base = build_base_to_full(modules)

    derived = {}
    # One partition per kept module.
    for base in sorted(kept_bases):
        # Each base may have multiple slang-suffixed RTLIL instances;
        # take the union of macros reachable from any of them.
        union = set()
        for full in by_base.get(base, []):
            union |= collect_macros_under(
                full, modules, by_base, kept_bases, macro_bases,
            )
        if union:
            derived[base] = sorted(union)

    # Top residue.
    if top is not None:
        # by_base lookup of the design top base — pick the slang-top form.
        top_full_candidates = by_base.get(_base(top), [])
        # The actual top module has the `\\top` attribute and was identified
        # by name during parsing — start from that exact full name.
        start = top if top in modules else (top_full_candidates[0] if top_full_candidates else None)
        if start is not None:
            top_macros = collect_macros_under(
                start, modules, by_base, kept_bases, macro_bases,
            )
            if top_macros:
                derived["_top"] = sorted(top_macros)
    return derived


def format_dict(d):
    """Format the dict as paste-ready Starlark."""
    if not d:
        return "kept_macros = {}"
    lines = ["kept_macros = {"]
    for k in sorted(d):
        lines.append("    \"{}\": [".format(k))
        for m in d[k]:
            lines.append("        \"{}\",".format(m))
        lines.append("    ],")
    lines.append("}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtlil", required=True)
    ap.add_argument("--kept-modules", required=True,
                    help="JSON: {\"modules\": [...]} (same shape as kept_modules.json)")
    ap.add_argument("--macros", required=True,
                    help="JSON: [\"macro_name\", ...] — base names of macros in deps")
    ap.add_argument("--user-kept-macros", required=True,
                    help="JSON: {\"M\": [\"macro\", ...], ...} user-supplied dict")
    ap.add_argument("--top", required=True, help="Design top module name (base form)")
    ap.add_argument("--output", required=True,
                    help="Output validated_kept_macros.json (success only)")
    args = ap.parse_args()

    with open(args.kept_modules) as f:
        kept_modules = json.load(f)["modules"]
    with open(args.macros) as f:
        macros = json.load(f)
    with open(args.user_kept_macros) as f:
        user_dict = json.load(f)

    modules, top_full = parse_rtlil(args.rtlil)
    # Prefer the explicit --top base; if RTLIL had `\\top` annotation,
    # use that exact full name. Otherwise fall back to --top.
    start_top = top_full if top_full is not None else args.top
    derived = derive_kept_macros(modules, start_top, kept_modules, macros)

    # Normalise both dicts to sorted-list-of-sorted-lists for comparison.
    # Strip the synthetic "_top" key — it's reported as informational
    # output for the top-level residue, but the user is explicitly told
    # not to pass it back to orfs_flow, so it must not factor into the
    # comparison.
    def norm(d):
        return {k: sorted(v) for k, v in d.items() if v and k != "_top"}

    if norm(derived) == norm(user_dict):
        with open(args.output, "w") as f:
            json.dump({k: sorted(v) for k, v in derived.items()}, f, indent=2)
        return 0

    # Mismatch: emit a paste-ready dict and error.
    sys.stderr.write(
        "ERROR: kept_macros does not match what canonicalize RTLIL shows.\n"
        "Replace the kept_macros argument with the following (the '_top'\n"
        "key represents the top-level residue partition — macros\n"
        "instantiated above any kept module — and is informational only;\n"
        "do not pass it back to orfs_flow):\n\n"
    )
    sys.stderr.write(format_dict(derived))
    sys.stderr.write("\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
