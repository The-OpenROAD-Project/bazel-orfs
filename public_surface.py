#!/usr/bin/env python3
"""Keep MODULE.bazel's dev/non-dev split honest against what ships.

A downstream root that depends on bazel-orfs resolves every non-dev
bazel_dep, extension repo and repo rule declared here, and can load any
.bzl file and any BUILD file with a public target. Two things can go
wrong, and both have gone wrong here before:

1. A non-dev dependency nothing shipped uses. It costs every consumer a
   module in their graph and an MVS constraint they never asked for.
   The fix is `dev_dependency = True`, or deleting it.
2. A shipped file that references a dev-only repo. It loads and
   analyses fine from this root and fails downstream with "No
   repository visible as '@x'". The fix is making the repo non-dev, or
   making the file not shipped (private visibility, or under test/).

"Shipped" is decided from the tree, not from a list: a BUILD file with a
`//visibility:public` target, every top-level .bzl, every .bzl beside a
shipped BUILD, and everything those load() transitively. test/ is never
shipped, so a public target under it is a third violation.

Run from a checkout:

    bazelisk run //:public_surface

CI runs it after lint. It reads the tree through git, so it sees what a
commit would ship and nothing else.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

# Apparent repo names always resolvable from any module.
_BUILTIN_REPOS = {"bazel_tools"}

# A dev-only repo whose name legitimately appears in shipped files, and
# why. The generated design BUILDs load from @orfs_designs, which only
# bazel-orfs as root declares (see docs/orfs-design-builds.md); the
# generator and the DSL it emits have to spell that name.
_ALLOWED_DEV_REFERENCES = {
    "orfs_designs": {
        "orfs_source.bzl",
        "orfs_design_builds.bzl",
        "private/designs.bzl",
        "private/design_dsl.bzl",
        "private/orfs_design.bzl",
    },
    # Created by the orfs_repositories extension and named in a label it
    # hands to the sibling @config repo it also creates. Repos of one
    # extension see each other by name, so this never resolves through
    # MODULE.bazel's use_repo at all.
    "mock_klayout": {"extension.bzl"},
}

_BUILD_NAMES = {"BUILD", "BUILD.bazel"}
_TEST_DIR = "test"

_APPARENT_REPO = re.compile(r"(?<![\w@])@([A-Za-z][\w.-]*)")
_PUBLIC = re.compile(r'"//visibility:public"')


def _statements(text):
    """Top-level statements of a Starlark file, bracket-balanced."""
    out, buf, depth = [], [], 0
    for line in text.splitlines(keepends=True):
        if depth == 0 and buf and line.strip():
            out.append("".join(buf))
            buf = []
        buf.append(line)
        depth += line.count("(") + line.count("[") + line.count("{")
        depth -= line.count(")") + line.count("]") + line.count("}")
    if buf:
        out.append("".join(buf))
    return out


def _consumer_facing(text):
    """The parts of a BUILD file a downstream root evaluates or can depend on.

    Every load() runs when the package loads, so each one counts. Of the
    targets, only public ones can be depended on from outside; a private
    target may reference whatever it likes without a consumer noticing.
    A public default_visibility makes every target count.
    """
    if re.search(r'default_visibility\s*=\s*\[[^\]]*"//visibility:public"', text):
        return text
    return "".join(
        s
        for s in _statements(text)
        if s.lstrip().startswith("load(") or _PUBLIC.search(s)
    )


def _strip_comments(text):
    """Drop `# ...` comments that start a line or follow whitespace.

    Good enough for Starlark: a `#` glued to non-space is left alone so
    a shell heredoc inside a string keeps its content.
    """
    return re.sub(r"(^|\s)#.*$", r"\1", text, flags=re.M)


def _call_bodies(text, callee):
    """Yield the argument text of every top-level `callee(...)` call."""
    for m in re.finditer(r"^%s\(" % re.escape(callee), text, re.M):
        depth = 0
        for i in range(m.end() - 1, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    yield text[m.end() : i]
                    break


def _is_dev(body):
    return re.search(r"\bdev_dependency\s*=\s*True\b", body) is not None


def _name(body):
    m = re.search(r'\bname\s*=\s*"([^"]+)"', body)
    return m.group(1) if m else None


class Module:
    """What MODULE.bazel declares, split into dev and non-dev repos."""

    def __init__(self, text):
        text = _strip_comments(text)
        self.text = text
        self.name = _name(next(_call_bodies(text, "module"), "")) or ""
        self.bazel_deps = {}  # name -> is_dev
        for body in _call_bodies(text, "bazel_dep"):
            self.bazel_deps[_name(body)] = _is_dev(body)

        # Extension proxies and repo-rule proxies: `x = use_extension(...)`
        # and `x = use_repo_rule(...)`, each carrying its own dev flag.
        ext_dev = {}
        for m in re.finditer(
            r"^(\w+)\s*=\s*use_extension\((.*?)\)\s*$", text, re.M | re.S
        ):
            ext_dev[m.group(1)] = _is_dev(m.group(2))
        repo_rules = set(re.findall(r"^(\w+)\s*=\s*use_repo_rule\(", text, re.M))

        self.repos = {}  # apparent repo name -> is_dev
        for m in re.finditer(r"^use_repo\(\s*(\w+)\s*,(.*?)\)", text, re.M | re.S):
            dev = ext_dev.get(m.group(1), False)
            for repo in re.findall(r'"([^"]+)"', m.group(2)):
                self.repos[repo] = dev
        for rule in repo_rules:
            for body in _call_bodies(text, rule):
                self.repos[_name(body)] = _is_dev(body)

    def visible_downstream(self):
        """Apparent repo names a non-root bazel-orfs can still see."""
        names = set(_BUILTIN_REPOS) | {self.name}
        names |= {n for n, dev in self.bazel_deps.items() if not dev}
        names |= {n for n, dev in self.repos.items() if not dev}
        return names

    def declared(self):
        return set(self.bazel_deps) | set(self.repos)


def _bazelignore(root):
    path = root / ".bazelignore"
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]


def _nested_module_dirs(files):
    return {
        f.parent for f in files if f.name == "MODULE.bazel" and str(f.parent) != "."
    }


def _in_any(path, dirs):
    return any(path == d or d in path.parents for d in dirs)


def _load_targets(text):
    """Labels of every load() in a Starlark file."""
    return re.findall(r'^\s*load\(\s*"([^"]+)"', _strip_comments(text), re.M)


def _resolve_load(label, from_dir, module_name):
    """The repo-relative path a load() label names, or None if external."""
    if label.startswith("@"):
        prefix = "@" + module_name + "//"
        if not label.startswith(prefix):
            return None
        label = "//" + label[len(prefix) :]
    if label.startswith("//"):
        pkg, _, file = label[2:].partition(":")
        return Path(pkg) / file if pkg else Path(file)
    if label.startswith(":"):
        return from_dir / label[1:]
    return None


def shipped_files(root, files, module_name):
    """Repo-relative paths of BUILD/.bzl files a downstream root can load."""
    ignored = [Path(p) for p in _bazelignore(root)]
    nested = _nested_module_dirs(files)
    skip = ignored + sorted(nested) + [Path(_TEST_DIR)]

    def candidate(f):
        return f.suffix == ".bzl" or f.name in _BUILD_NAMES

    tree = {f for f in files if candidate(f) and not _in_any(f, skip)}
    texts = {f: (root / f).read_text(errors="replace") for f in tree}

    shipped = set()
    for f in tree:
        if f.name in _BUILD_NAMES and _PUBLIC.search(texts[f]):
            shipped.add(f)
    public_dirs = {f.parent for f in shipped}
    for f in tree:
        if f.suffix == ".bzl" and (str(f.parent) == "." or f.parent in public_dirs):
            shipped.add(f)

    # Transitive closure over load(): a shipped file makes everything it
    # loads shipped too, wherever it lives.
    queue = list(shipped)
    while queue:
        f = queue.pop()
        for label in _load_targets(texts[f]):
            target = _resolve_load(label, f.parent, module_name)
            if target is not None and target in texts and target not in shipped:
                shipped.add(target)
                queue.append(target)
    return {f: texts[f] for f in sorted(shipped)}


def check(root, files):
    """Violations as human-readable lines; empty when the tree is clean."""
    module = Module((root / "MODULE.bazel").read_text())
    visible = module.visible_downstream()
    declared = module.declared()
    shipped = shipped_files(root, files, module.name)
    problems = []

    # 1. Shipped files reference only what a downstream root can see.
    referenced = set()
    for f, text in shipped.items():
        text = _strip_comments(text)
        if f.name in _BUILD_NAMES:
            text = _consumer_facing(text)
        for repo in sorted(set(_APPARENT_REPO.findall(text))):
            referenced.add(repo)
            if repo in visible:
                continue
            if str(f) in _ALLOWED_DEV_REFERENCES.get(repo, ()):
                continue
            kind = "dev-only" if repo in declared else "undeclared"
            problems.append(
                "%s: references @%s, which is %s in MODULE.bazel, so it fails "
                "downstream with \"No repository visible as '@%s'\""
                % (f, repo, kind, repo)
            )

    # 2. Every non-dev bazel_dep is used by something shipped, or by
    #    MODULE.bazel itself (an extension tag such as orfs.default's
    #    yosys_plugins, or a use_extension on it).
    module_refs = set(_APPARENT_REPO.findall(module.text))
    for name, dev in sorted(module.bazel_deps.items()):
        if dev or name in referenced or name in module_refs:
            continue
        problems.append(
            "MODULE.bazel: bazel_dep %r is non-dev but nothing shipped references "
            "@%s; mark it dev_dependency = True or delete it" % (name, name)
        )

    # 3. Nothing under test/ is public.
    for f in files:
        if f.name in _BUILD_NAMES and f.parts[0] == _TEST_DIR:
            if _PUBLIC.search(_strip_comments((root / f).read_text(errors="replace"))):
                problems.append(
                    "%s: public target under %s/; test infrastructure is not shipped"
                    % (f, _TEST_DIR)
                )
    return problems


def tracked_files(root):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [Path(p.decode()) for p in out.split(b"\0") if p]


def main(argv):
    root = Path(
        argv[1] if len(argv) > 1 else os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    ).resolve()
    problems = check(root, tracked_files(root))
    for p in problems:
        print(p)
    if problems:
        print("\n%d public-surface violation(s); see public_surface.py" % len(problems))
        return 1
    print("public surface: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
