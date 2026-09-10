#!/usr/bin/env python3
"""Which OpenSTA containers can make a result depend on the thread count.

Class 1 of the four bug classes in bazel-orfs#970 is hash-iteration order
over a pointer-keyed container: `std::hash<T*>` hashes the *address*, so
the bucket layout -- and therefore the iteration order -- depends on
allocation order, which depends on thread scheduling. Deterministic at
one thread, arbitrary above. TSAN cannot see it; it is not a race. It is
the shape behind OpenSTA 7e5cf132 (per-vertex path index keyed by `Tag*`)
and 128ea3cf, and upstream deleted `hashPtr` in May 2026 with the comment
"pointer hashing causes results to change from run to run; use
Network::id functions instead".

This audit needs no flow runs, so it is the part of the campaign that can
produce evidence on day one. It reports, per declaration:

    key       pointer or value. A pointer key with the default hash is
              hashed by address.
    hash      the explicit hash argument, or `std::hash` when there is
              none. A named hash is not automatically safe -- it is
              safe when it hashes *content* (`PinIdHash`) rather than an
              address -- so the name is printed and not judged.
    iterated  a range-for or a `begin()` over a variable of this type,
              with the file:line that proves it. A lookup-only container
              cannot leak its bucket order into a result.

The columns are printed, not collapsed into a verdict, and every row
carries the declaration text: this is a heuristic scan of C++ with
regular expressions, so it is built to be *checked* by a reader rather
than believed. `iterated` says "not observed", never "no".

And `iterated` is a **shortlist of loops to read, not a defect count**.
Bucket order is only a bug when it survives the loop body:
`sortByPathName` iterates a pointer-keyed set directly into a `sort`,
and `Power::reportActivityAnnotation` accumulates into counters. Both
are on the list and both are correct. The one on the list that is not
is `Sim::clearSimValues`, which calls an observer per element in
whatever order the allocator produced.

Two false positives shaped this scan and are worth knowing before
trusting the next one: a local named `visited` in `search/ClkSkew.cc`
matched a `VertexSet visited` iterated in `search/Sta.cc`, and the
parameter `set` in `network/NetworkCmp.cc` matched a namesake in
`liberty/Liberty.cc`. Both came from searching a *local* variable's
name tree-wide. Locals are now confined to their own file and searched
from their declaration onward; only members (a trailing underscore, by
OpenSTA convention) are searched across files.

Audited against the OpenSTA commit the flow actually builds -- parsed out
of the `archive_override` in MODULE.bazel, and verified against the
sha256 that is pinned there beside it, so the audit cannot drift from the
binary and cannot silently audit a different tree.

    bazelisk run //test/threads_policy:sta_audit
    bazelisk run //test/threads_policy:sta_audit -- --sta ~/OpenROAD/src/sta
"""

import argparse
import collections
import json
import os
import re
import subprocess
import sys

# The container spellings that expose bucket order. std::map and
# std::set are ordered by the comparator and so cannot: they are not
# scanned, and a fix in this area is usually a move to one of them.
_OPENERS = re.compile(r"\b((?:std::)?unordered_(?:map|set)|Unordered(?:Map|Set))\s*<")

# `for (auto x : name)` / `for (const Pin *p : name)` -- any range-for
# whose range expression is exactly this variable. The character class
# excludes newlines deliberately: without that it spans lines, and a
# `for` on one line pairs with a `: name)` several lines below it,
# which both invents iteration that is not there and reports the line
# of the `for` rather than of the loop that matched.
_RANGE_FOR = r"for\s*\([^;{}\n]*:\s*(?:\*)?%s\s*\)"

# The other way bucket order reaches a caller.
_ITERATOR = r"\b%s\s*\.\s*(?:c?r?begin)\s*\("

# A declaration of the form `SomeAliasName foo_;`, `SomeAliasName &foo`,
# `static SomeAliasName foo`. Deliberately not a full declarator
# grammar: it finds the names to look for iteration on, and a name it
# misses shows up as "not observed", which is the safe direction.
_DECLARED_AS = r"\b%s\s*[&*]?\s*(\w+)\s*[;,){=]"

# Where the OpenSTA source lives that is not the tool: test fixtures and
# examples may hash pointers freely, and counting them would inflate
# every number in the table.
_NOT_TOOL = ("/test/", "/examples/", "/tclreadline/")

Site = collections.namedtuple(
    "Site", "path line container key key_type hash names iterated evidence decl"
)


def pinned_sta_commit(module_text):
    """The OpenSTA commit `archive_override` vendors into src/sta.

    Parsed rather than configured: a constant here would be one more
    thing a `//:bump` has to remember, and an audit of the wrong tree
    is worse than no audit.
    """
    hits = set(
        re.findall(r"\.openroad-submodule-src-sta-([0-9a-f]{40})\.tar\.gz", module_text)
    )
    if not hits:
        raise SystemExit(
            "MODULE.bazel names no src-sta submodule tarball: the openroad "
            "archive_override's patch_cmds shape changed"
        )
    if len(hits) > 1:
        raise SystemExit(
            "MODULE.bazel names {} different src-sta commits: {}".format(
                len(hits), ", ".join(sorted(hits))
            )
        )
    return hits.pop()


def pinned_sta_sha256(module_text, commit):
    """The sha256 MODULE.bazel pins for that tarball.

    `archive_override`'s own `integrity` does not cover patch_cmds
    bytes, which is why the override verifies each vendored tarball with
    `sha256sum -c`. The audit verifies the same bytes the same way.
    """
    pattern = r"([0-9a-f]{64})\s+\.openroad-submodule-src-sta-%s\.tar\.gz" % commit
    hits = set(re.findall(pattern, module_text))
    if len(hits) != 1:
        raise SystemExit(
            "MODULE.bazel does not pin exactly one sha256 for src-sta "
            "{}: found {}".format(commit, len(hits))
        )
    return hits.pop()


def workspace():
    """The repo root, whether run via bazel or directly."""
    return os.environ.get("BUILD_WORKSPACE_DIRECTORY") or os.getcwd()


def fetch_sta(commit, sha256, root, verbose=False):
    """Unpack the pinned OpenSTA under ./tmp, once; return its directory.

    Reuses an existing unpack so a re-run is free, and verifies the
    tarball before trusting it. `curl` and `tar` only: the same two
    tools the override itself uses.
    """
    dest = os.path.join(root, "sta-{}".format(commit))
    if os.path.isdir(os.path.join(dest, "search")):
        if verbose:
            print("reusing {}".format(dest))
        return dest
    os.makedirs(dest, exist_ok=True)
    tarball = os.path.join(root, "sta-{}.tar.gz".format(commit))
    url = "https://github.com/The-OpenROAD-Project/OpenSTA/archive/{}.tar.gz".format(
        commit
    )
    subprocess.run(
        ["curl", "-sSfL", "--retry", "5", "--retry-connrefused", "-o", tarball, url],
        check=True,
    )
    subprocess.run(
        ["sha256sum", "-c", "-"],
        input="{}  {}\n".format(sha256, tarball),
        text=True,
        check=True,
    )
    subprocess.run(
        ["tar", "xzf", tarball, "--strip-components=1", "-C", dest], check=True
    )
    os.remove(tarball)
    return dest


def tool_sources(root):
    """Every non-test C++ file under an OpenSTA tree, repo-relative."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in sorted(filenames):
            if not name.endswith((".hh", ".cc", ".h", ".cpp")):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if any(part in "/" + rel for part in _NOT_TOOL):
                continue
            out.append(rel)
    return sorted(out)


def _balanced(text, start):
    """The text between `text[start]` == '<' and its matching '>'.

    Template arguments wrap across lines in this codebase (Sdc.hh's
    EdgeExceptionsMap, Power.hh's PwrSeqActivityMap), so the scan is
    over characters and not over lines. Returns (args, end_index), or
    (None, None) when the brackets never balance -- a macro or a
    comparison operator rather than a declaration.
    """
    depth = 0
    for i in range(start, len(text)):
        char = text[i]
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i
    return None, None


def split_args(args):
    """Top-level comma split of a template argument list."""
    out = []
    depth = 0
    current = []
    for char in args:
        if char in "<([":
            depth += 1
        elif char in ">)]":
            depth -= 1
        if char == "," and depth == 0:
            out.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if "".join(current).strip():
        out.append("".join(current).strip())
    return out


def key_kind(key_type):
    """ "pointer" when the key is an address, else "value"."""
    stripped = re.sub(r"\bconst\b", "", key_type).strip()
    return "pointer" if stripped.endswith("*") else "value"


def hash_kind(container, args):
    """The explicit hash argument, or "std::hash" when defaulted.

    Not judged: `PinIdHash` hashes a Network id and is stable, `TagHash`
    hashes content and is stable given the same element set, and a hash
    named after a pointer is not. Which one it is takes reading it, so
    the name is carried into the table for a human to read.
    """
    position = 2 if container.lower().endswith("map") else 1
    if len(args) > position and args[position]:
        return args[position]
    return "std::hash"


def alias_name(line_prefix):
    """The alias this declaration defines, if it is a `using` at all."""
    match = re.search(r"\busing\s+(\w+)\s*=\s*$", line_prefix)
    return match.group(1) if match else None


def declared_name(after):
    """The variable a bare (non-alias) declaration names, if any."""
    match = re.match(r"\s*[&*]?\s*(\w+)", after)
    return match.group(1) if match else None


def find_sites(rel_path, text):
    """Every unordered-container declaration in one file."""
    sites = []
    for match in _OPENERS.finditer(text):
        container = match.group(1)
        args, end = _balanced(text, match.end() - 1)
        if args is None:
            continue
        line = text.count("\n", 0, match.start()) + 1
        line_start = text.rfind("\n", 0, match.start()) + 1
        prefix = text[line_start : match.start()]
        # A commented-out or documentation mention is not a declaration.
        if "//" in prefix or "*" == prefix.strip()[-1:]:
            continue
        parts = split_args(args)
        if not parts:
            continue
        names = []
        alias = alias_name(prefix)
        if alias:
            names.append(alias)
        else:
            bare = declared_name(text[end + 1 : end + 64])
            if bare:
                names.append(bare)
        decl = re.sub(r"\s+", " ", text[line_start : end + 1].strip())
        sites.append(
            Site(
                path=rel_path,
                line=line,
                container=container,
                key=key_kind(parts[0]),
                key_type=parts[0],
                hash=hash_kind(container, parts),
                names=names,
                iterated=False,
                evidence=None,
                decl=decl,
            )
        )
    return sites


def is_member(name):
    """OpenSTA names members with a trailing underscore, locals without.

    The distinction is what makes the search safe. A member is used
    across the header/implementation boundary, so it has to be looked
    for tree-wide; a local or a parameter cannot escape its file, and
    searching tree-wide for one finds a *different* variable that
    happens to share the name. Both false positives the first version
    of this audit produced were exactly that: `visited` in
    `search/ClkSkew.cc` (never iterated) matched a `VertexSet visited`
    iterated in `search/Sta.cc`, and the parameter `set` in
    `network/NetworkCmp.cc` matched a `LibertyPortSet *set` in
    `liberty/Liberty.cc`.
    """
    return name.endswith("_")


def iteration_evidence(texts, name, scope=None, after_line=0):
    """Where a variable of this name is iterated, or None.

    `scope` restricts the search to one file, which is mandatory for a
    local or a parameter. `after_line` starts the search at the
    declaration: one file holds many functions, and `network/NetworkCmp.cc`
    alone declares four different parameters named `set`, so the first
    `set` in the file is usually somebody else's. A local is iterated
    after it is declared, or not at all.

    Only the first hit is reported: one proof is enough to move the row
    into the column that has to be read.
    """
    if not name:
        return None
    searched = texts if scope is None else {scope: texts.get(scope, "")}
    for pattern in (_RANGE_FOR, _ITERATOR):
        expression = re.compile(pattern % re.escape(name))
        for rel_path, text in sorted(searched.items()):
            for match in expression.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                if line <= after_line:
                    continue
                return "{}:{}".format(rel_path, line)
    return None


def variables_of(texts, alias):
    """(path, line, name) for every variable declared with this alias."""
    out = []
    expression = re.compile(_DECLARED_AS % re.escape(alias))
    for rel_path, text in sorted(texts.items()):
        for match in expression.finditer(text):
            out.append(
                (rel_path, text.count("\n", 0, match.start()) + 1, match.group(1))
            )
    return out


def resolve_iteration(sites, texts):
    """Fill in `iterated`/`evidence` for every site.

    A container is only iterated through a *variable*, never through the
    alias that names its type, so an alias site is resolved in two
    steps: find the variables declared with it, then look for iteration
    of those -- tree-wide for a member, same-file for anything else.
    The evidence names the variable and both lines, so a reader can
    check the loop rather than take the row's word for it.
    """
    out = []
    for site in sites:
        evidence = None
        for name in site.names:
            # A bare declaration already names its own variable, and
            # that variable is local to this file unless it is a member.
            scope = None if is_member(name) else site.path
            hit = iteration_evidence(
                texts, name, scope, 0 if scope is None else site.line - 1
            )
            if hit:
                evidence = "`{}` at {}".format(name, hit)
                break
            for decl_path, decl_line, var in variables_of(texts, name):
                member = is_member(var)
                hit = iteration_evidence(
                    texts,
                    var,
                    None if member else decl_path,
                    0 if member else decl_line - 1,
                )
                if hit:
                    evidence = "`{}` at {}, declared {}:{}".format(
                        var, hit, decl_path, decl_line
                    )
                    break
            if evidence:
                break
        out.append(site._replace(iterated=bool(evidence), evidence=evidence))
    return out


def risk(site):
    """The class-1 *exposure* of one site. Not a verdict, a shortlist.

    `iterated` address-hashed and iterated somewhere: the loop has to
               be read, because iteration alone is not a defect. The
               order has to survive the loop body. `sortByPathName`
               (`network/NetworkCmp.cc:97`) iterates a pointer-keyed
               set straight into a `sort`, and is correct; the counting
               loop at `power/Power.cc:1702` accumulates into totals,
               and is correct. The shape that is *not* correct is an
               order-dependent side effect, like the observer callback
               at `search/Sim.cc:778`.
    `latent`   address-hashed, no iteration observed: correct today and
               one range-for away from not being.
    `low`      keyed by value, or hashed by a named hash whose
               stability is a property of that hash rather than of the
               allocator.
    """
    if site.key != "pointer":
        return "low"
    if site.hash != "std::hash":
        return "low"
    return "iterated" if site.iterated else "latent"


def audit(root):
    """Every site in an OpenSTA tree, with iteration resolved."""
    texts = {}
    for rel_path in tool_sources(root):
        with open(os.path.join(root, rel_path), errors="replace") as handle:
            texts[rel_path] = handle.read()
    sites = []
    for rel_path, text in texts.items():
        sites += find_sites(rel_path, text)
    sites = resolve_iteration(sites, texts)
    return sorted(sites, key=lambda s: (risk(s) != "iterated", s.path, s.line))


def heading_label(commit):
    """A commit is abbreviated; anything else is printed in full.

    The `--sta` path is deliberately not a commit, and truncating it to
    ten characters would turn "which tree is this?" -- the one question
    the heading exists to answer -- into a shrug.
    """
    return commit[:10] if re.fullmatch(r"[0-9a-f]{40}", commit) else commit


def markdown(sites, commit):
    """The table the pull request carries."""
    counts = collections.Counter(risk(s) for s in sites)
    out = [
        "### Class 1: pointer-keyed containers in OpenSTA `{}`".format(
            heading_label(commit)
        ),
        "",
        "{} declarations outside test code: {} address-hashed and iterated "
        "somewhere (`iterated`), {} address-hashed with no iteration "
        "observed (`latent`), {} keyed by value or by a named hash "
        "(`low`).".format(
            len(sites),
            counts["iterated"],
            counts["latent"],
            counts["low"],
        ),
        "",
        "**`iterated` is a shortlist, not a defect count.** Iteration in "
        "bucket order is only a bug when the order survives the loop: "
        "`sortByPathName` iterates a pointer-keyed set straight into a "
        "`sort`, and the activity loop in `power/Power.cc` accumulates "
        "into counters. Both are order-independent and both are on this "
        "list. The loop body decides, and no regular expression can read "
        "it.",
        "",
        "`iterated` cites the first proof found -- the variable, where it "
        "is iterated, and where it was declared -- and says *not "
        "observed* rather than *no*. The declaration text is printed for "
        "every row so a reader can check the scan instead of believing "
        "it.",
        "",
        "| risk | site | key | hash | iterated | declaration |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for site in sites:
        out.append(
            "| {} | `{}:{}` | {} | `{}` | {} | `{}` |".format(
                risk(site),
                site.path,
                site.line,
                site.key,
                site.hash,
                site.evidence or "not observed",
                site.decl.replace("|", "\\|"),
            )
        )
    return "\n".join(out) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sta",
        default=None,
        help="an OpenSTA tree to audit; default is the commit MODULE.bazel pins",
    )
    parser.add_argument("--json", default=None, help="also write the sites here")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    root = workspace()
    with open(os.path.join(root, "MODULE.bazel")) as handle:
        module_text = handle.read()
    commit = pinned_sta_commit(module_text)

    if args.sta:
        sta_root = os.path.expanduser(args.sta)
        # An arbitrary tree is not the pinned one, and a table that does
        # not say so invites the reader to attribute its rows to the
        # binary the flow builds.
        commit = "unpinned tree {}".format(sta_root)
    else:
        sta_root = fetch_sta(
            commit,
            pinned_sta_sha256(module_text, commit),
            os.path.join(root, "tmp", "threads_policy"),
            args.verbose,
        )

    sites = audit(sta_root)
    if not sites:
        raise SystemExit(
            "no unordered containers found under {}: not an OpenSTA "
            "tree".format(sta_root)
        )
    sys.stdout.write(markdown(sites, commit))
    if args.json:
        with open(args.json, "w") as handle:
            json.dump(
                {
                    "sta_commit": commit,
                    "sites": [dict(s._asdict(), risk=risk(s)) for s in sites],
                },
                handle,
                indent=2,
                sort_keys=True,
            )


if __name__ == "__main__":
    main()
