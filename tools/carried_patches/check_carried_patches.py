"""Classify each carried patch against the tree it is meant to apply to.

Bazel's ``ctx.patch`` locates a hunk by content near its target line, so a
hunk whose context appears in more than one place can apply to the wrong one
and still report success. A patch that has been absorbed upstream is equally
quiet: the fetch is clean either way, and the damage surfaces much later as
an unrelated build error.

The four verdicts a carried patch can earn:

``CLEAN``
    The pre-image occurs exactly once. The patch applies where intended.
``ABSORBED``
    The pre-image is gone and the post-image is present: upstream took the
    change. Delete the carry.
``AMBIGUOUS``
    The pre-image occurs more than once. Which one ``ctx.patch`` picks is not
    something to leave to chance -- widen the hunk's context.
``NEEDS_REBASE``
    Neither image is present. Upstream moved the code.
"""

import argparse
import os
import re
import sys

CLEAN = "CLEAN"
ABSORBED = "ABSORBED"
AMBIGUOUS = "AMBIGUOUS"
NEEDS_REBASE = "NEEDS_REBASE"

_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def parse_patch(text, renames=None):
    """Split a unified diff into ``(path, pre_image, post_image)`` hunks.

    ``pre_image``/``post_image`` are the hunk's context and removed/added
    lines, in order -- what the file must look like before and after. A
    hunk ends where its header's line counts say, as for ``patch``: what
    follows, such as ``git format-patch``'s ``-- `` signature, is not in it.
    A file the diff renames is recorded in ``renames`` (new path -> old):
    its hunks are against the old path's content.
    """
    renames = {} if renames is None else renames
    hunks = []
    path = source = None
    pre, post = [], []
    old_left = new_left = 0

    for line in text.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("\\"):
                continue
            tag, body = (line[:1], line[1:]) if line else (" ", "")
            if tag in " -":
                pre.append(body)
                old_left -= 1
            if tag in " +":
                post.append(body)
                new_left -= 1
            if old_left <= 0 and new_left <= 0:
                hunks.append((path, tuple(pre), tuple(post)))
            continue
        if line.startswith("rename from "):
            source = line[len("rename from ") :]
            continue
        if line.startswith("rename to "):
            renames[line[len("rename to ") :]] = source
            continue
        if line.startswith("--- "):
            source = line[4:].strip().split("\t")[0]
            source = source[2:] if source.startswith("a/") else source
            continue
        if line.startswith("+++ "):
            target = line[4:].strip().split("\t")[0]
            path = target[2:] if target.startswith("b/") else target
            if source not in (path, "/dev/null"):
                renames[path] = source
            continue
        header = _HUNK_RE.match(line)
        if header:
            old_left = int(header.group(1) or 1)
            new_left = int(header.group(2) or 1)
            pre, post = [], []
    return hunks


def count_occurrences(haystack_lines, needle_lines):
    """How many places in the file the block of lines occurs."""
    if not needle_lines:
        return 0
    n, span = 0, len(needle_lines)
    for i in range(len(haystack_lines) - span + 1):
        if haystack_lines[i : i + span] == list(needle_lines):
            n += 1
    return n


def classify_hunk(file_text, pre_image, post_image):
    lines = file_text.splitlines()
    matches = count_occurrences(lines, pre_image)
    if matches == 1:
        return CLEAN
    if matches > 1:
        return AMBIGUOUS
    if post_image and count_occurrences(lines, post_image) >= 1:
        return ABSORBED
    return NEEDS_REBASE


# Worst-first: a patch is only as trustworthy as its least trustworthy hunk,
# and AMBIGUOUS is the verdict with no natural failure signal.
_SEVERITY = [AMBIGUOUS, NEEDS_REBASE, ABSORBED, CLEAN]


def classify_patch(patch_text, read_file):
    """Verdict for a whole patch. ``read_file(path)`` returns text or None."""
    verdicts = []
    renames = {}
    for path, pre, post in parse_patch(patch_text, renames):
        text = read_file(renames.get(path, path))
        if text is None:
            # A hunk with an empty pre-image creates the file, so upstream
            # not having it is the state the patch expects, not a stale hunk.
            verdicts.append((path, CLEAN if not pre else NEEDS_REBASE))
            continue
        verdicts.append((path, classify_hunk(text, pre, post)))
    if not verdicts:
        return NEEDS_REBASE, []
    worst = min((v for _, v in verdicts), key=_SEVERITY.index)
    return worst, verdicts


def apply_patch(patch_text, read_file, overlay):
    """Record a CLEAN patch's post-images in ``overlay``.

    ``overlay`` maps a path to its text, or to None once a rename moved it.

    A series is applied in order, each patch to the tree the ones before it
    left, so the next patch in the series is checked against that tree and
    not against the pristine one.
    """
    renames = {}
    for path, pre, post in parse_patch(patch_text, renames):
        source = path if path in overlay else renames.get(path, path)
        text = read_file(source)
        lines = text.splitlines() if text is not None else []
        if pre:
            span = len(pre)
            for i in range(len(lines) - span + 1):
                if lines[i : i + span] == list(pre):
                    lines[i : i + span] = list(post)
                    break
        else:
            lines = list(post)
        overlay[path] = "\n".join(lines) + "\n"
        if source != path:
            overlay[source] = None
    for path, source in renames.items():
        if path not in overlay:
            overlay[path] = read_file(source)
            overlay[source] = None


def patch_labels(module_bazel_text):
    """Every ``//...:*.patch`` label mentioned in MODULE.bazel, in order.

    A patch inlined into ``patch_cmds`` as base64 (a submodule the archive
    does not carry) is found by its ``# Extracted from //...:x.patch``
    comment, the only place its source file is named.
    """
    seen, labels = set(), []
    for quoted, extracted in re.findall(
        r'"(//[^"]+\.patch)"|Extracted from (//\S+\.patch)', module_bazel_text
    ):
        label = quoted or extracted
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


_CALL_RE = re.compile(r"^([A-Za-z_][\w.]*)\(", re.MULTILINE)


def patch_groups(module_bazel_text):
    """Map each patch label to the tree it is applied to.

    A carried patch is only meaningful against the dependency whose override
    lists it, and MODULE.bazel names that dependency right there:
    ``module_name = "openroad"`` in an override, or the extension tag's own
    name. Classifying every patch against one tree reports the patches aimed
    elsewhere as NEEDS_REBASE, which buries a real verdict in noise.
    """
    groups = {}
    for match in _CALL_RE.finditer(module_bazel_text):
        end = module_bazel_text.find("\n)", match.end())
        if end == -1:
            continue
        block = module_bazel_text[match.start() : end]
        labels = [l for l in patch_labels(block)]
        if not labels:
            continue
        name = re.search(r'module_name\s*=\s*"([^"]+)"', block) or re.search(
            r'\bname\s*=\s*"([^"]+)"', block
        )
        key = name.group(1) if name else match.group(1).split(".")[0]
        groups.setdefault(key, []).extend(
            l for l in labels if l not in groups.get(key, [])
        )
    return groups


def label_to_path(label):
    """``//patches:foo.patch`` -> ``patches/foo.patch``."""
    package, _, name = label[2:].partition(":")
    return os.path.join(package, name) if package else name


def _reader(root, overlay):

    def read(path):
        if path in overlay:
            return overlay[path]
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            return None
        with open(full, encoding="utf-8", errors="replace") as handle:
            return handle.read()

    return read


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--tree",
        action="append",
        default=[],
        required=True,
        help="Pristine (unpatched) tree as <group>=<path>, where <group> is "
        "the dependency MODULE.bazel names (openroad, yosys, qt-bazel...). "
        "Repeatable. A bare <path> applies to every group.",
    )
    parser.add_argument(
        "--module-file", default="MODULE.bazel", help="Path to MODULE.bazel."
    )
    parser.add_argument(
        "--patch",
        action="append",
        help="Check only this patch file. Repeatable, in the order the "
        "patches apply; skips MODULE.bazel.",
    )
    args = parser.parse_args(argv)
    os.chdir(os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."))

    trees = {}
    default_tree = None
    for spec in args.tree:
        group, sep, root = spec.partition("=")
        if sep:
            trees[group] = root
        else:
            default_tree = group

    if args.patch:
        work = [(None, p) for p in args.patch]
    else:
        with open(args.module_file, encoding="utf-8") as handle:
            groups = patch_groups(handle.read())
        work = [(g, label_to_path(l)) for g, labels in groups.items() for l in labels]

    overlays = {}
    worst_seen = CLEAN
    missing = False
    skipped = {}
    for group, path in work:
        root = trees.get(group, default_tree)
        if root is None:
            skipped.setdefault(group, 0)
            skipped[group] += 1
            continue
        if not os.path.isfile(path):
            missing = True
            print(f"{'MISSING':13} {path}")
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            patch_text = handle.read()
        read_file = _reader(root, overlays.setdefault(root, {}))
        verdict, per_file = classify_patch(patch_text, read_file)
        if verdict == CLEAN:
            apply_patch(patch_text, read_file, overlays[root])
        if _SEVERITY.index(verdict) < _SEVERITY.index(worst_seen):
            worst_seen = verdict
        if verdict != CLEAN:
            detail = ", ".join(f"{p}: {v}" for p, v in per_file if v != CLEAN)
            print(f"{verdict:13} {path}  ({detail})")

    for group, count in sorted(skipped.items()):
        print(f"{'SKIPPED':13} {group}: {count} patches, no --tree {group}=<path>")

    return 0 if worst_seen == CLEAN and not missing else 1


if __name__ == "__main__":
    sys.exit(main())
