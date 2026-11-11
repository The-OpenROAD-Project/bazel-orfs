#!/usr/bin/env python3
"""Path-based names for the numbered modules of a deduplicating generator.

A generator that deduplicates modules (Chisel and firtool) names the
survivors of one desired name X, X_1, X_2, ... in elaboration order, so
an instance added anywhere renumbers every later X_<n>. Each renumbered
module, every module that instantiates one, and every name a keep list,
a report or a per-module cache key holds then changes, though the
hardware did not.

This pass gives each module of a contested family, a desired name with
more than one module in the design, the name of where it sits instead:

    <desired name>__<parent's name>__<first instance name, sorted>

computed top-down, so a parent's new name feeds its children's. A module
of a contested family that several parents instantiate is cloned, one
copy per parent. A name over MAX_NAME_LENGTH keeps its desired name and
its instance name and hashes the parent, as Verilator's V3Param does.

The desired name of a module comes from a groups file, {module: desired
name}, which Chisel knows exactly (DedupGroupAnnotation). Without one, X
and X_<n> are taken to be one family. Modules named by an exclude
pattern (fnmatch), modules without a definition in the sources and the
top keep their names.

The output holds the modules the top reaches, renamed, in the order of
their sources, and the text between modules verbatim. The same inputs
give the same bytes.

  stable_module_names.py --top TOP --out OUT.sv --map module_names.json
      [--groups groups.json] [--exclude PATTERN]... [--keep NAME]...
      [--retime PATTERN]...
      SOURCE...

A SOURCE is a .v/.sv file or a directory of them. module_names.json maps
every renamed module to its new names. A --keep name or --retime
pattern that matches no module of the output stops the pass, with the
new names of a renamed one.
"""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys

MAX_NAME_LENGTH = 100

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
    | (?P<comment>//[^\n]*|/\*.*?\*/)
    | (?P<attr>\(\*.*?\*\))
    | (?P<string>"(?:\\.|[^"\\])*")
    | (?P<directive>`[A-Za-z_][A-Za-z0-9_$]*)
    | (?P<ident>[A-Za-z_][A-Za-z0-9_$]*|\\\S+)
    | (?P<other>.)
    """,
    re.VERBOSE | re.DOTALL,
)

_NUMBERED = re.compile(r"^(.*)_[0-9]+$")


class StableNamesError(Exception):
    pass


def tokens(text):
    """(kind, value, start) for each token of a Verilog text, comments,
    attributes and whitespace left out."""
    for m in _TOKEN.finditer(text):
        kind = m.lastgroup
        if kind in ("ws", "comment", "attr"):
            continue
        yield kind, m.group(), m.start()


class Module:
    def __init__(self, name, source, start, end, text):
        self.name = name
        self.source = source
        self.start = start
        self.end = end
        self.text = text
        # (child module, instance name, offset of the child's name in text)
        self.instances = []


def parse(sources):
    """The module definitions of [(path, text)] by name, and the bind
    statements' module names."""
    modules = {}
    binds = []
    for index, (path, text) in enumerate(sources):
        toks = list(tokens(text))
        i = 0
        while i < len(toks):
            kind, value, start = toks[i]
            if kind == "ident" and value == "bind":
                j = i + 1
                while j < len(toks) and toks[j][1] != ";":
                    if toks[j][0] == "ident":
                        binds.append(toks[j][1])
                    j += 1
                i = j
                continue
            if kind != "ident" or value not in ("module", "macromodule"):
                i += 1
                continue
            j = i + 1
            while j < len(toks) and toks[j][1] in ("static", "automatic"):
                j += 1
            if j >= len(toks) or toks[j][0] != "ident":
                raise StableNamesError(f"{path}: a module without a name")
            name = toks[j][1]
            k = j + 1
            while k < len(toks) and not (
                toks[k][0] == "ident" and toks[k][1] == "endmodule"
            ):
                k += 1
            if k >= len(toks):
                raise StableNamesError(f"{path}: module {name} has no endmodule")
            end = toks[k][2] + len("endmodule")
            if name in modules:
                raise StableNamesError(
                    f"module {name} is defined in both "
                    f"{modules[name].source[1]} and {path}"
                )
            module = Module(name, (index, path), start, end, text[start:end])
            module.body_tokens = [(kd, v, s - start) for kd, v, s in toks[j + 1 : k]]
            modules[name] = module
            i = k + 1
    for module in modules.values():
        module.instances = _instances(module.body_tokens, modules)
        del module.body_tokens
    return modules, binds


def _instances(toks, modules):
    """The instances of defined modules among a module body's tokens:
    `Child [#(...)] name [range] (`."""
    found = []
    for i, (kind, value, offset) in enumerate(toks):
        if kind != "ident" or value not in modules:
            continue
        j = i + 1
        if j < len(toks) and toks[j][1] == "#":
            j += 1
            if j >= len(toks) or toks[j][1] != "(":
                continue
            j = _skip_balanced(toks, j, "(", ")")
        if j >= len(toks) or toks[j][0] != "ident":
            continue
        instance = toks[j][1]
        j += 1
        while j < len(toks) and toks[j][1] == "[":
            j = _skip_balanced(toks, j, "[", "]")
        if j < len(toks) and toks[j][1] == "(":
            found.append((value, instance, offset))
    return found


def _skip_balanced(toks, j, open_, close):
    depth = 0
    while j < len(toks):
        if toks[j][1] == open_:
            depth += 1
        elif toks[j][1] == close:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return j


def families(names, groups=None):
    """{module: desired name} for every module of a contested family."""
    if groups is not None:
        desired = {n: groups[n] for n in names if n in groups}
    else:
        desired = {}
        for n in names:
            m = _NUMBERED.match(n)
            desired[n] = m.group(1) if m else n
    members = {}
    for n, d in desired.items():
        members.setdefault(d, []).append(n)
    return {n: d for n, d in desired.items() if len(members[d]) > 1}


def stable_name(desired, parent, instance):
    name = f"{desired}__{parent}__{instance}"
    if len(name) <= MAX_NAME_LENGTH:
        return name
    digest = hashlib.sha256(name.encode()).hexdigest()[:12]
    name = f"{desired}__{digest}__{instance}"
    if len(name) <= MAX_NAME_LENGTH:
        return name
    return f"{desired[: MAX_NAME_LENGTH - len(digest) - 2]}__{digest}"


def rename(sources, top, groups=None, exclude=()):
    """Renames the modules of contested families in [(path, text)].

    Returns the renamed sources, [(path, text)] in the same order, and
    {old name: [new names]} for every renamed module.
    """
    modules, binds = parse(sources)
    if top not in modules:
        raise StableNamesError(f"top module {top} is not defined in the sources")
    contested = {
        n: d
        for n, d in families(sorted(modules), groups).items()
        if n != top and not any(fnmatch.fnmatchcase(n, p) for p in exclude)
    }
    bound = sorted(set(binds) & set(contested))
    if bound:
        raise StableNamesError(
            "bind statements name modules this pass renames: " + " ".join(bound)
        )

    emitted = {}  # new name -> (old name, text)
    renamed = {}  # old name -> set of new names

    def emit(name, new):
        if new in emitted:
            if emitted[new][0] != name:
                raise StableNamesError(
                    f"{emitted[new][0]} and {name} would both be named {new}"
                )
            return
        if new != name and new in modules:
            raise StableNamesError(f"{name}'s new name {new} is already a module")
        emitted[new] = (name, None)
        module = modules[name]
        first = {}
        for child, instance, _ in module.instances:
            if child not in first or instance < first[child]:
                first[child] = instance
        children = {}
        for child in sorted(first):
            if child in contested:
                children[child] = stable_name(contested[child], new, first[child])
            else:
                children[child] = child
        text = module.text
        edits = [
            (offset, len(child), children[child])
            for child, _, offset in module.instances
            if children[child] != child
        ]
        name_offset = text.index(name, len("module"))
        out = []
        last = 0
        for offset, length, replacement in sorted(edits):
            out.append(text[last:offset])
            out.append(replacement)
            last = offset + length
        out.append(text[last:])
        text = "".join(out)
        if new != name:
            text = text[:name_offset] + new + text[name_offset + len(name) :]
            renamed.setdefault(name, set()).add(new)
        emitted[new] = (name, text)
        for child in sorted(children):
            emit(child, children[child])

    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10000))
    emit(top, top)

    by_old = {}
    for new in sorted(emitted):
        old, text = emitted[new]
        by_old.setdefault(old, []).append(text)

    out = []
    for index, (path, text) in enumerate(sources):
        defined = sorted(
            (m for m in modules.values() if m.source[0] == index),
            key=lambda m: m.start,
        )
        pieces = []
        last = 0
        for module in defined:
            pieces.append(text[last : module.start])
            pieces.append("\n\n".join(by_old.get(module.name, [])))
            last = module.end
        pieces.append(text[last:])
        out.append((path, "".join(pieces)))
    return out, {old: sorted(new) for old, new in sorted(renamed.items())}


def check_kept(kept, sources, mapping):
    """The names in kept, fnmatch patterns, that match no module of the
    renamed sources, each with why."""
    defined, _ = parse(sources)
    missing = []
    for name in kept:
        if name in defined or fnmatch.filter(defined, name):
            continue
        if name in mapping:
            missing.append(f"{name}: renamed to {' '.join(mapping[name])}")
        else:
            missing.append(f"{name}: no such module")
    return missing


def read_sources(paths):
    sources = []
    for path in paths:
        if os.path.isdir(path):
            found = []
            for root, dirs, files in os.walk(path):
                dirs.sort()
                found.extend(
                    os.path.join(root, f)
                    for f in sorted(files)
                    if f.endswith((".v", ".sv"))
                )
            files = sorted(found)
        else:
            files = [path]
        for f in files:
            with open(f) as fp:
                sources.append((f, fp.read()))
    return sources


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--top", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--map", required=True)
    parser.add_argument("--groups")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--keep", action="append", default=[])
    parser.add_argument("--retime", action="append", default=[])
    parser.add_argument("sources", nargs="+")
    args = parser.parse_args(argv)

    groups = None
    if args.groups:
        with open(args.groups) as fp:
            groups = json.load(fp)
    try:
        sources, mapping = rename(
            read_sources(args.sources), args.top, groups, args.exclude
        )
        missing = check_kept(args.keep + args.retime, sources, mapping)
    except StableNamesError as e:
        print(f"stable_module_names: {e}", file=sys.stderr)
        return 1
    if missing:
        print(
            "stable_module_names: kept or retimed modules missing after renaming "
            "(module_names.json lists every new name):\n  " + "\n  ".join(missing),
            file=sys.stderr,
        )
        return 1
    with open(args.out, "w") as fp:
        for path, text in sources:
            fp.write(f"// {os.path.basename(path)}\n")
            fp.write(text)
            if not text.endswith("\n"):
                fp.write("\n")
    with open(args.map, "w") as fp:
        json.dump(mapping, fp, indent=2, sort_keys=True)
        fp.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
