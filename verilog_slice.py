#!/usr/bin/env python3
"""Cut a design's Verilog into one self-contained source per kept module.

Each slice holds the kept module and every module under it, down to the
next kept module, which appears as a stub: its header (parameter and port
declarations) and nothing else. A slice is then all a partition needs to
canonicalize its module, and its bytes change only when one of the
modules in it does, or a kept child's ports do.

The sources must be one module per definition with nothing between the
definitions but comments: what a CIRCT firtool split or concatenated
output is. Anything else outside a module (a `define, an `include, a
package) or a directive that reaches across modules fails here, rather
than leaving a slice that elaborates differently from the whole design.

Usage: verilog_slice.py --slice MODULE OUT [--slice MODULE OUT ...] SOURCE...

A SOURCE that is a directory stands for its .v, .sv and .svh files.
"""

import argparse
import os
import re
import sys

# Directives allowed inside a module: a conditional reads only defines
# from the command line, which every slice sees as the whole design does.
CONDITIONAL_DIRECTIVES = {"ifdef", "ifndef", "elsif", "else", "endif"}

# Compiler directives (IEEE 1800-2017 clause 22). Any of these other than
# a conditional can change how text elsewhere elaborates.
DIRECTIVES = CONDITIONAL_DIRECTIVES | {
    "begin_keywords",
    "celldefine",
    "default_nettype",
    "define",
    "end_keywords",
    "endcelldefine",
    "include",
    "line",
    "nounconnected_drive",
    "pragma",
    "resetall",
    "timescale",
    "unconnected_drive",
    "undef",
    "undefineall",
}

IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_$]*|\\\S+"
MODULE_RE = re.compile(
    r"\b(?:macro)?module\s+(?:(?:static|automatic)\s+)?(" + IDENTIFIER + ")"
)
ENDMODULE_RE = re.compile(r"\bendmodule\b(\s*:\s*(?:" + IDENTIFIER + "))?")
TOKEN_RE = re.compile(IDENTIFIER)
DIRECTIVE_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_$]*)")
PORT_KEYWORD_RE = re.compile(r"\b(?:input|output|inout)\b")


class SliceError(Exception):
    pass


def _bare(name):
    return name[1:] if name.startswith("\\") else name


def mask(text):
    """text with comments and string literals blanked out, same length.

    Newlines are kept, so offsets and line numbers carry over. Escaped
    identifiers are copied as they are: a `//` inside one is not a
    comment.
    """
    out = list(text)
    i = 0
    n = len(text)

    def blank(start, end):
        for k in range(start, end):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        if c == "\\":
            while i < n and not text[i].isspace():
                i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise SliceError("unterminated /* comment")
            blank(i, end + 2)
            i = end + 2
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                elif text[j] == "\n":
                    raise SliceError("unterminated string")
                j += 1
            if j >= n:
                raise SliceError("unterminated string")
            blank(i + 1, j)
            i = j + 1
        else:
            i += 1
    return "".join(out)


class Module:
    def __init__(self, name, path, line, text, masked, header_end, name_end):
        self.name = name
        self.name_end = name_end
        self.path = path
        self.line = line
        self.text = text
        self.masked = masked
        self.header_end = header_end

    def has_parameters(self):
        return self.masked[self.name_end : self.header_end].lstrip().startswith("#")

    def stub(self):
        """The module's declaration with its body left out."""
        return self.text[: self.header_end] + "\nendmodule\n"

    def instances(self, names):
        """(module, instance name) of each instantiation, in source order."""
        body = self.masked[self.header_end :]
        found = []
        for m in TOKEN_RE.finditer(body):
            name = _bare(m.group(0))
            if name not in names:
                continue
            before = body[: m.start()].rstrip()
            if (
                before
                and not before.endswith((";", ")"))
                and not re.search(r"\b(?:begin|end|else|generate)$", before)
            ):
                continue
            rest = body[m.end() :]
            i = len(rest) - len(rest.lstrip())
            if rest.startswith("#", i):
                i = rest.index("(", i)
                depth = 0
                while True:
                    depth += {"(": 1, ")": -1}.get(rest[i], 0)
                    i += 1
                    if depth == 0:
                        break
            inst = re.match(
                r"\s*(" + IDENTIFIER + r")\s*(?:\[[^\]]*\]\s*)?\(", rest[i:]
            )
            if inst:
                found.append((name, _bare(inst.group(1))))
        return found

    def children(self, names):
        body = self.masked[self.header_end :]
        found = {_bare(t) for t in TOKEN_RE.findall(body)}
        found.discard(self.name)
        return found & names


def _where(path, text, offset):
    return "{}:{}".format(path, text.count("\n", 0, offset) + 1)


def _header_end(path, text, masked, name_end):
    """Offset just past the `;` that ends the module's header.

    Also refuses a non-ANSI port list: its declarations are in the body,
    so a stub of the header alone would have ports without directions.
    """
    depth = 0
    ports = None
    i = name_end
    while i < len(masked):
        c = masked[i]
        if c == "(":
            if depth == 0 and ports is None and masked[i - 1 : i] != "#":
                j = i - 1
                while j >= name_end and masked[j].isspace():
                    j -= 1
                if masked[j] != "#":
                    ports = [i + 1, None]
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and ports is not None and ports[1] is None:
                ports[1] = i
        elif c == ";" and depth == 0:
            if ports is not None:
                port_text = masked[ports[0] : ports[1]]
                if port_text.strip() and not PORT_KEYWORD_RE.search(port_text):
                    raise SliceError(
                        "{}: non-ANSI port list; a stub of this module would "
                        "have no port directions".format(_where(path, text, name_end))
                    )
            return i + 1
        i += 1
    raise SliceError(
        "{}: module header has no `;`".format(_where(path, text, name_end))
    )


def parse_modules(path, text):
    masked = mask(text)
    modules = []
    pos = 0
    attribute_start = None
    while True:
        while pos < len(masked) and masked[pos].isspace():
            pos += 1
        if pos >= len(masked):
            if attribute_start is not None:
                raise SliceError(
                    "{}: attribute with no module after it".format(
                        _where(path, text, attribute_start)
                    )
                )
            return modules
        if masked.startswith("(*", pos):
            end = masked.find("*)", pos + 2)
            if end < 0:
                raise SliceError("{}: unterminated (*".format(_where(path, text, pos)))
            if attribute_start is None:
                attribute_start = pos
            pos = end + 2
            continue
        m = MODULE_RE.match(masked, pos)
        if not m:
            snippet = text[pos : text.find("\n", pos) if "\n" in text[pos:] else None]
            raise SliceError(
                "{}: `{}` is outside any module; slices need sources with "
                "nothing between module definitions but comments".format(
                    _where(path, text, pos), snippet.strip()
                )
            )
        end = ENDMODULE_RE.search(masked, m.end())
        if not end:
            raise SliceError("{}: no endmodule".format(_where(path, text, pos)))
        nested = MODULE_RE.search(masked, m.end(), end.start())
        if nested:
            raise SliceError(
                "{}: nested module declaration".format(
                    _where(path, text, nested.start())
                )
            )
        start = pos if attribute_start is None else attribute_start
        module_masked = masked[start : end.end()]
        for d in DIRECTIVE_RE.finditer(module_masked):
            if d.group(1) in DIRECTIVES and d.group(1) not in CONDITIONAL_DIRECTIVES:
                raise SliceError(
                    "{}: `{} reaches beyond its module".format(
                        _where(path, text, start + d.start()), d.group(1)
                    )
                )
        module_text = text[start : end.end()]
        header_end = _header_end(path, text, masked, m.end()) - start
        modules.append(
            Module(
                _bare(m.group(1)),
                path,
                text.count("\n", 0, start) + 1,
                module_text,
                module_masked,
                header_end,
                m.end() - start,
            )
        )
        attribute_start = None
        pos = end.end()


def expand_sources(sources):
    files = []
    for source in sources:
        if os.path.isdir(source):
            found = []
            for root, _, names in os.walk(source):
                for name in names:
                    if name.endswith((".v", ".sv", ".svh")):
                        found.append(os.path.join(root, name))
            files.extend(sorted(found))
        else:
            files.append(source)
    return files


def read_modules(files):
    modules = {}
    order = []
    for path in files:
        with open(path) as f:
            text = f.read()
        for module in parse_modules(path, text):
            if module.name in modules:
                first = modules[module.name]
                raise SliceError(
                    "module {} is defined twice: {}:{} and {}:{}".format(
                        module.name, first.path, first.line, module.path, module.line
                    )
                )
            modules[module.name] = module
            order.append(module.name)
    return modules, order


def elaborated_names(modules, top):
    """Each module's name as slang elaborates the whole design from `top`.

    slang names a module's body after the hierarchical path of the
    instance it first elaborates, depth first in source order, and every
    later instance shares that body: `Def$Top.a.b`, and the top its bare
    name. A slice is elaborated from its own module, so its module and
    stubs are renamed to these names for its partition to fit the design.
    """
    names = set(modules)
    elaborated = {top: top}
    stack = [(top, iter(modules[top].instances(names)))]
    while stack:
        path, instances = stack[-1]
        for child, instance in instances:
            if child not in elaborated:
                child_path = path + "." + instance
                elaborated[child] = "{}${}".format(child, child_path)
                stack.append((child_path, iter(modules[child].instances(names))))
                break
        else:
            stack.pop()
    return elaborated


def slice_text(modules, order, target, kept, elaborated=None):
    """The slice of `target`: its subtree, kept descendants as stubs."""
    names = set(modules)
    full = {target}
    stubs = set()
    todo = [target]
    while todo:
        for child in sorted(modules[todo.pop()].children(names)):
            if child in full or child in stubs:
                continue
            if child in kept:
                stubs.add(child)
            else:
                full.add(child)
                todo.append(child)
    parts = []
    if elaborated is not None:
        for name in [target] + [n for n in order if n in stubs]:
            parts.append("// verilog_slice: {} {}\n".format(name, elaborated[name]))
    for name in order:
        if name in full:
            parts.append(modules[name].text + "\n")
        elif name in stubs:
            parts.append(modules[name].stub())
    return "".join(parts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--slice",
        nargs=2,
        action="append",
        default=[],
        metavar=("MODULE", "OUT"),
        help="a kept module and the file its slice goes to",
    )
    parser.add_argument(
        "--top", required=True, help="the design's top module, which names the rest"
    )
    parser.add_argument("sources", nargs="+")
    args = parser.parse_args(argv)

    try:
        modules, order = read_modules(expand_sources(args.sources))
        kept = {name for name, _ in args.slice}
        missing = sorted(kept - set(modules))
        if missing:
            raise SliceError(
                "kept modules not defined in the sources: " + " ".join(missing)
            )
        if args.top not in modules:
            raise SliceError(
                "top module {} is not defined in the sources".format(args.top)
            )
        elaborated = elaborated_names(modules, args.top)
        for name in sorted(kept):
            if name not in elaborated:
                raise SliceError(
                    "kept module {} is not under {}".format(name, args.top)
                )
            if modules[name].has_parameters():
                raise SliceError(
                    "kept module {} has parameters; its slice would elaborate "
                    "it with their defaults".format(name)
                )
        for name, out in args.slice:
            text = slice_text(modules, order, name, kept, elaborated)
            with open(out, "w") as f:
                f.write(text)
    except SliceError as e:
        print(
            "verilog_slice: {}\nverilog_slice: build without verilog_slices, "
            "which canonicalizes each kept module out of the whole design".format(e),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
