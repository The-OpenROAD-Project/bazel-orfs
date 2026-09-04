#!/usr/bin/env python3
"""Update bazel-orfs and OpenROAD versions in MODULE.bazel.

Also enforces lockstep between the ``yosys`` and ``abc`` bazel_deps when
both are declared by a downstream MODULE.bazel.  YosysHQ/yosys's abc
submodule pins a specific abc revision per yosys release; the BCR
``abc/0.NN-yosyshq`` modules expose those revisions individually.  Mixing
a ``yosys = "0.NN"`` bazel_dep with an unrelated ``abc = "0.MM-yosyshq"``
override has caused real synthesis-quality regressions, so we treat it as
a hard error rather than a warning.

Usage:
    python bump.py [--module-file MODULE.bazel]

Run via Bazel:
    bazelisk run //:bump
"""

import argparse
import base64
import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

# Map yosys MAJOR.MINOR -> the abc module version it ships against.  Update
# this whenever a new (yosys, abc) pair lands on a BCR registry.  Only list
# pairs that are *actually published* on BCR — yosys 0.63 is on BCR but no
# matching abc 0.63-yosyshq is, so omit it (the check then yields the
# 'unknown pairing' message rather than a stale 'expected X' suggestion).
# The right-hand value matches the BCR ``abc`` module ``version`` field.
YOSYS_ABC_PAIRS = {
    "0.62": "0.62-yosyshq",
    "0.64": "0.64-yosyshq.bcr.2",
    "0.68": "0.68-yosyshq.bcr.1",
}


# The bumper supports a rolling window of MODULE.bazel shapes: a consumer
# whose bazel-orfs pin is older than this many days is outside it.  bump.py
# always downloads the newest bump_impl.py, so the only compatibility
# surface is the *consumer's file*, and migration paths for shapes older
# than the window are deleted rather than maintained.  See the cleanup
# policy in CLAUDE.md and docs/openroad.md.
BUMP_SUPPORT_WINDOW_DAYS = 30


# Written by a bazel-orfs self-bump: the commit date of the ORFS pin it
# just wrote.  It is the tree's own dated anchor, which //:bump_compat_test
# measures COMPAT markers against so that the cleanup policy is decided by
# commit dates rather than by whenever CI happens to run.
BUMP_REFERENCE_DATE_FILE = "bump_reference_date.txt"


class StalePinError(RuntimeError):
    """Raised when the bazel-orfs pin predates the supported window."""


class BumpError(RuntimeError):
    """Raised when an expected MODULE.bazel rewrite finds no match.

    The bumper guards each ``update_*`` call site with :func:`_expect` so
    a missing ``git_override`` / ``archive_override`` / ``bazel_dep``
    block surfaces as a loud failure instead of a silent no-op.
    ``bazelisk run //:bump --ignore`` downgrades it to a warning.
    """


def _expect(condition, description, ignore_errors=False):
    """Assert that ``condition`` is truthy, or fail (or warn under --ignore).

    Used as a precondition check before each ``update_*`` call site that
    the bumper has already decided must apply: existence of the target
    ``git_override`` / ``archive_override`` / ``bazel_dep`` block.  If the
    block is absent the MODULE.bazel is in an unexpected shape — e.g. the
    consumer renamed a module or hand-wired a variable — and silently
    no-oping would hide the divergence.  Under ``--ignore`` we warn and
    keep going so partially-updatable files still get the parts we know.
    """
    if condition:
        return
    msg = f"Expected {description} in MODULE.bazel but found no match"
    if ignore_errors:
        print(f"WARNING: {msg}", file=sys.stderr)
        return
    raise BumpError(msg)


def detect_project(content):
    """Detect project type from MODULE.bazel content.

    Returns 'bazel-orfs', 'openroad', or 'downstream'.
    """
    match = re.search(
        r'^module\s*\(.*?name\s*=\s*"([^"]*)"',
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return "downstream"
    name = match.group(1)
    if name == "bazel-orfs":
        return "bazel-orfs"
    if name == "openroad":
        return "openroad"
    return "downstream"


def read_git_override_commit(content, module_name):
    """Return the commit a git_override pins, or None.

    Handles both ``commit = "<sha>"`` and the variable-bound
    ``commit = SOME_VAR`` shape (resolving the top-level assignment), which
    is what OpenROAD's MODULE.bazel uses.
    """
    span = find_git_override_block(content, module_name)
    if not span:
        return None
    block = content[span[0] : span[1]]
    m = re.search(r'commit\s*=\s*"([^"]*)"', block)
    if m:
        return m.group(1)
    m_var = re.search(r"commit\s*=\s*([A-Za-z_][A-Za-z_0-9]*)", block)
    if not m_var:
        return None
    m_assign = re.search(
        r"^" + re.escape(m_var.group(1)) + r'\s*=\s*"([^"]*)"',
        content,
        flags=re.MULTILINE,
    )
    return m_assign.group(1) if m_assign else None


def fetch_commit_date(repo, sha):
    """Committer date of ``sha`` in ``repo`` as an aware UTC datetime."""
    data = fetch_json(f"https://api.github.com/repos/{repo}/commits/{sha}")
    stamp = data["commit"]["committer"]["date"]
    return datetime.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc
    )


def _stale_pin_message(reason, remedy):
    """Compose the hard-stop text pointing at the rolling-window policy."""
    return (
        f"{reason}\n\n"
        f"//:bump supports a {BUMP_SUPPORT_WINDOW_DAYS}-day rolling window of "
        "MODULE.bazel shapes, measured between commit dates — never against "
        "the clock.  Migration paths for older shapes are deleted, not "
        "maintained, so bumping from this pin is unsupported and may corrupt "
        "MODULE.bazel.\n\n"
        f"{remedy}\n"
        "  * Or step forward: hand-edit the bazel-orfs commit to one no more\n"
        f"    than {BUMP_SUPPORT_WINDOW_DAYS} days newer than the current pin, "
        "re-run //:bump, and\n"
        "    repeat until current.\n"
        "  * --allow-stale-pin proceeds anyway: unsupported, best-effort, and\n"
        "    on you to review the resulting diff.\n\n"
        'Policy: docs/openroad.md, "Supported window".  Read it before '
        "working around this check."
    )


def write_reference_date(workspace_dir, moment):
    """Record ``moment``'s date as the tree's compat-cleanup anchor."""
    path = os.path.join(workspace_dir, BUMP_REFERENCE_DATE_FILE)
    with open(path, "w") as f:
        f.write(
            "# Commit date of the ORFS pin in MODULE.bazel, written by "
            "//:bump.\n"
            "# The anchor //:bump_compat_test measures COMPAT markers "
            "against, so\n"
            "# that the cleanup policy runs on commit dates and not on the "
            "clock.\n"
            f"{moment.date().isoformat()}\n"
        )
    return path


def read_reference_date(text):
    """Parse the anchor written by :func:`write_reference_date`."""
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return datetime.date.fromisoformat(line)
    raise ValueError("no date found in reference-date file")


def check_pin_window(
    content,
    target_commit,
    fetch_commit_date_fn=fetch_commit_date,
    window_days=BUMP_SUPPORT_WINDOW_DAYS,
):
    """Hard-stop when the consumer's bazel-orfs pin is outside the window.

    The span measured is between two *commit dates*: the pinned bazel-orfs
    commit and ``target_commit``, the commit this bump would move it to.
    Wall-clock time is deliberately not an input — the same pair of commits
    must always yield the same verdict, so that a bump is reproducible and
    the policy cannot quietly change under a build that is merely re-run
    later.

    Only the bazel-orfs pin is measured: it is the one commit that dates
    the *shape* of the file, since every other override in a consumer's
    MODULE.bazel is written by whichever bump_impl.py that bazel-orfs
    shipped.  Returns the span in days on success.
    """
    if detect_project(content) == "bazel-orfs":
        return None
    commit = read_git_override_commit(content, "bazel-orfs")
    if commit is None:
        # No readable pin: _expect at the call sites reports the missing
        # block far more precisely than a window check could.
        return None

    repo = "The-OpenROAD-Project/bazel-orfs"
    try:
        pinned_at = fetch_commit_date_fn(repo, commit)
    except Exception as e:
        raise StalePinError(
            _stale_pin_message(
                f"Cannot date the pinned bazel-orfs commit {commit} ({e}). "
                "It is not a commit on The-OpenROAD-Project/bazel-orfs, so "
                "neither its date — nor the shape of this MODULE.bazel — "
                "can be checked.",
                "  * Re-pin bazel-orfs to a commit on the upstream repository.",
            )
        ) from e
    target_at = fetch_commit_date_fn(repo, target_commit)

    span = (target_at - pinned_at).days
    if span > window_days:
        raise StalePinError(
            _stale_pin_message(
                f"The pinned bazel-orfs commit {commit[:12]} "
                f"({pinned_at.date().isoformat()}) is {span} days behind the "
                f"commit this bump targets, {target_commit[:12]} "
                f"({target_at.date().isoformat()}).",
                "  * Re-seed MODULE.bazel from the current template in "
                "bazel-orfs's\n"
                "    README.md, re-apply your local edits, then re-run //:bump.",
            )
        )
    return span


def update_git_override_commit(content, module_name, new_commit):
    """Update commit in git_override() block for a given module_name.

    Handles both active and commented-out blocks.  When the block uses
    a variable reference (``commit = SOME_VAR``) instead of a string
    literal, the top-level assignment ``SOME_VAR = "..."`` is updated.
    """
    # Track variable names that need updating (from variable-reference blocks).
    vars_to_update = set()

    def replace_in_block(m):
        block = m.group(0)
        if f'module_name = "{module_name}"' not in block:
            return block
        # Try replacing a quoted literal first.
        new_block, n = re.subn(
            r'(commit\s*=\s*")[^"]*(")',
            rf"\g<1>{new_commit}\2",
            block,
        )
        if n:
            return new_block
        # No quoted literal — look for a variable reference.
        var_match = re.search(r"commit\s*=\s*([A-Za-z_][A-Za-z_0-9]*)", block)
        if var_match:
            vars_to_update.add(var_match.group(1))
        return block

    # Active git_override blocks
    content = re.sub(
        r"git_override\(.*?\)",
        replace_in_block,
        content,
        flags=re.DOTALL,
    )

    # Commented-out git_override blocks
    def replace_commented_block(m):
        block = m.group(0)
        if f'module_name = "{module_name}"' not in block:
            return block
        new_block, n = re.subn(
            r'(commit\s*=\s*")[^"]*(")',
            rf"\g<1>{new_commit}\2",
            block,
        )
        if n:
            return new_block
        var_match = re.search(r"commit\s*=\s*([A-Za-z_][A-Za-z_0-9]*)", block)
        if var_match:
            vars_to_update.add(var_match.group(1))
        return block

    content = re.sub(
        r"#\s*git_override\((?:\n#.*?)*?\n#\s*\)",
        replace_commented_block,
        content,
    )

    # Update any top-level variable assignments discovered above.
    for var_name in vars_to_update:
        content = re.sub(
            r"(" + re.escape(var_name) + r'\s*=\s*")[^"]*(")',
            rf"\g<1>{new_commit}\2",
            content,
        )

    return content


def has_bazel_dep(content, module_name):
    """Check if content has an active (uncommented) bazel_dep for the given module."""
    return bool(
        re.search(
            r'^bazel_dep\(.*?name\s*=\s*"' + re.escape(module_name) + r'"',
            content,
            re.MULTILINE,
        )
    )


def find_starlark_call_end(content, start):
    """Find the closing paren of a Starlark function call starting at `start`.

    Handles nested parens, brackets, braces, and triple-quoted strings.
    Returns the index after the closing paren.
    """
    depth = 0
    i = start
    n = len(content)
    while i < n:
        c = content[i]
        # Skip triple-quoted strings
        if content[i : i + 3] in ('"""', "'''"):
            quote = content[i : i + 3]
            i += 3
            end = content.find(quote, i)
            if end == -1:
                return n
            i = end + 3
            continue
        # Skip single-quoted strings
        if c in ('"', "'"):
            i += 1
            while i < n and content[i] != c:
                if content[i] == "\\":
                    i += 1
                i += 1
            i += 1
            continue
        # Skip comments
        if c == "#":
            while i < n and content[i] != "\n":
                i += 1
            continue
        if c in ("(", "[", "{"):
            depth += 1
        elif c in (")", "]", "}"):
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _position_is_in_comment(content, pos):
    """True if ``content[pos]`` is in a ``#`` line comment.

    Walks the current line from its start, tracking single- and double-quoted
    strings (so a ``#`` inside a string is not treated as a comment marker)
    and returns True the moment an unquoted ``#`` is seen before ``pos``.

    Used by the override-block finders below to skip regex matches that
    fall inside a comment — e.g. a documentation line that mentions
    ``archive_override(`` would otherwise be treated as the start of a real
    Starlark call, with ``find_starlark_call_end`` then walking past the
    comment lines into unrelated code and returning a runaway span.
    """
    line_start = content.rfind("\n", 0, pos) + 1
    in_str = None
    i = line_start
    while i < pos:
        c = content[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in ('"', "'"):
                in_str = c
            elif c == "#":
                return True
        i += 1
    return False


def find_git_override_block(content, module_name):
    """Find the full git_override() block for a module, handling nested strings.

    Returns (start, end) tuple or None if not found.
    """
    pattern = r"git_override\s*\("
    for m in re.finditer(pattern, content):
        if _position_is_in_comment(content, m.start()):
            continue
        end = find_starlark_call_end(content, m.start())
        block = content[m.start() : end]
        if f'module_name = "{module_name}"' in block:
            return (m.start(), end)
    return None


def find_archive_override_block(content, module_name):
    """Find the full archive_override() block for a module.

    Returns (start, end) tuple or None if not found.
    """
    pattern = r"archive_override\s*\("
    for m in re.finditer(pattern, content):
        if _position_is_in_comment(content, m.start()):
            continue
        end = find_starlark_call_end(content, m.start())
        block = content[m.start() : end]
        if f'module_name = "{module_name}"' in block:
            return (m.start(), end)
    return None


_GITHUB_ARCHIVE_URL_RE = re.compile(
    r"https://github\.com/[^/]+/[^/]+/archive/[^/]+\.tar\.gz"
)


def github_archive_url(github_repo, commit):
    """Compose the GitHub /archive/<sha>.tar.gz tarball URL for a commit."""
    return f"https://github.com/{github_repo}/archive/{commit}.tar.gz"


def github_archive_strip_prefix(github_repo, commit):
    """The directory prefix inside a GitHub /archive/<sha>.tar.gz tarball."""
    repo_basename = github_repo.split("/")[-1]
    return f"{repo_basename}-{commit}"


def compute_integrity(url):
    """Download URL and return SRI integrity (``sha256-<base64>``).

    Streams the response in chunks so the full archive (potentially tens of
    MB for ORFS) never materializes in memory.
    """
    h = hashlib.sha256()
    with urllib.request.urlopen(url) as resp:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return "sha256-" + base64.b64encode(h.digest()).decode("ascii")


def compute_sha256_hex(url):
    """Download URL and return sha256 hex digest.

    Hex (not SRI) so the value can be fed directly to ``sha256sum -c`` inside
    a patch_cmds line.  Streams the same way ``compute_integrity`` does.
    """
    h = hashlib.sha256()
    with urllib.request.urlopen(url) as resp:
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def fetch_submodule_sha(parent_repo, parent_commit, path):
    """Submodule SHA at ``path`` inside ``parent_repo`` at ``parent_commit``.

    Same shape as ``fetch_orfs_tool_sha`` (which is specialized to ORFS tools)
    but generic: used for OpenROAD's src/sta and third-party/abc.
    """
    url = (
        f"https://api.github.com/repos/{parent_repo}/contents/{path}"
        f"?ref={parent_commit}"
    )
    data = fetch_json(url)
    if data.get("type") != "submodule":
        raise RuntimeError(
            f"{parent_repo}/{path} is not a submodule at {parent_commit} "
            f"(got {data.get('type')!r})"
        )
    return data["sha"]


def update_archive_override(
    content,
    module_name,
    github_repo,
    new_commit,
    new_integrity,
):
    """Update urls, integrity, strip_prefix in archive_override(module_name=...).

    Targets the first ``"..."`` inside the ``urls = [...]`` list — single-URL
    mirror lists are the only shape used by bazel-orfs today.  Returns the
    content unchanged if no matching block exists.
    """
    span = find_archive_override_block(content, module_name)
    if not span:
        return content
    start, end = span
    block = content[start:end]

    new_url = github_archive_url(github_repo, new_commit)
    new_strip = github_archive_strip_prefix(github_repo, new_commit)

    block = re.sub(
        r'(urls\s*=\s*\[\s*")[^"]*(")',
        rf"\g<1>{new_url}\2",
        block,
        count=1,
    )
    block = re.sub(
        r'(integrity\s*=\s*")[^"]*(")',
        rf"\g<1>{new_integrity}\2",
        block,
        count=1,
    )
    block = re.sub(
        r'(strip_prefix\s*=\s*")[^"]*(")',
        rf"\g<1>{new_strip}\2",
        block,
        count=1,
    )

    return content[:start] + block + content[end:]


def _find_commit_var_in_block(block):
    """Return the variable name concatenated into strip_prefix/urls, or None.

    Detects the OpenROAD-style archive_override shape where the commit
    lives in a top-level variable spliced into two fields::

        strip_prefix = "OpenROAD-flow-scripts-" + ORFS_COMMIT,
        urls = [".../archive/" + ORFS_COMMIT + ".tar.gz"],
    """
    m = re.search(
        r"(?:strip_prefix|urls)\s*=[^,\n]*?\+\s*([A-Za-z_][A-Za-z_0-9]*)",
        block,
    )
    return m.group(1) if m else None


def _block_pins_commit(block, commit):
    """True if the block's ``urls`` already points at ``commit``.

    When it does, the digest fields describe the very tarball we would
    otherwise download and re-hash, so the whole fetch can be skipped.  The
    inverse case — a hand-edited url with a stale digest left behind — is
    caught loudly by Bazel's own integrity check on the next fetch.
    """
    m = re.search(r'urls\s*=\s*\[\s*"([^"]*)"', block)
    return bool(m and commit in m.group(1))


def _update_block_digest(
    block, github_repo, new_commit, fetch_integrity_fn, fetch_sha256_hex_fn
):
    """Rewrite whichever digest field an override block carries.

    Handles both ``integrity = "sha256-<base64>"`` (SRI) and
    ``sha256 = "<hex>"``.  Downloads the tarball once, for the digest kind
    actually present.
    """
    url = github_archive_url(github_repo, new_commit)
    if re.search(r'integrity\s*=\s*"', block):
        block = re.sub(
            r'(integrity\s*=\s*")[^"]*(")',
            rf"\g<1>{fetch_integrity_fn(url)}\2",
            block,
            count=1,
        )
    elif re.search(r'sha256\s*=\s*"', block):
        block = re.sub(
            r'(sha256\s*=\s*")[^"]*(")',
            rf"\g<1>{fetch_sha256_hex_fn(url)}\2",
            block,
            count=1,
        )
    return block


def find_orfs_source_tag(content):
    """Find the ``orfs.source(...)`` tag block.

    ORFS is consumed as an http_archive created by bazel-orfs's module
    extension rather than as a bazel_dep, because ``patches`` on an
    override is honoured only from the root module and would therefore
    land on whoever is root. The root module picks the version with a tag
    instead, so that is what this bumper rewrites.

    Returns ``(start, end)`` or ``None``.
    """
    for m in re.finditer(r"^\s*orfs\.source\s*\(", content, flags=re.MULTILINE):
        if _position_is_in_comment(content, m.start()):
            continue
        start = content.index("orfs.source", m.start())
        return (start, find_starlark_call_end(content, start))
    return None


def update_orfs_source_tag(
    content,
    orfs_commit,
    fetch_integrity_fn=compute_integrity,
    ignore_errors=False,
):
    """Rewrite the commit and integrity of an ``orfs.source()`` tag.

    Both attributes live in one call, so unlike the archive_override
    shapes there is no variable form to handle and no way for the two to
    half-update.

    Returns ``content`` unchanged if no tag exists (caller guards).
    """
    span = find_orfs_source_tag(content)
    if not span:
        return content
    start, end = span
    block = content[start:end]

    m_commit = re.search(r'commit\s*=\s*"([0-9a-f]{7,40})"', block)
    _expect(m_commit, 'commit = "<sha>" in orfs.source()', ignore_errors)
    if not m_commit:
        return content
    if m_commit.group(1) == orfs_commit:
        print("  orfs already at target commit; skipping re-hash")
        return content

    _expect(
        re.search(r'integrity\s*=\s*"', block),
        'integrity = "sha256-..." in orfs.source()',
        ignore_errors,
    )
    integrity = fetch_integrity_fn(github_archive_url(ORFS_REPO, orfs_commit))
    block = re.sub(
        r'(commit\s*=\s*")[^"]*(")',
        rf"\g<1>{orfs_commit}\2",
        block,
        count=1,
    )
    block = re.sub(
        r'(integrity\s*=\s*")[^"]*(")',
        rf"\g<1>{integrity}\2",
        block,
        count=1,
    )
    return content[:start] + block + content[end:]


def update_orfs_archive_override(
    content,
    orfs_commit,
    fetch_integrity_fn=compute_integrity,
    fetch_sha256_hex_fn=compute_sha256_hex,
    ignore_errors=False,
):
    """Update an ``archive_override(module_name = "orfs")`` block.

    Two shapes exist in the wild:

    * literal (bazel-orfs's own MODULE.bazel): commit embedded in the
      ``urls``/``strip_prefix`` string literals — rewrite them in place.
    * variable (OpenROAD's MODULE.bazel): a top-level ``ORFS_COMMIT = "..."``
      assignment concatenated into both fields — rewrite the assignment and
      the digest, leaving the concatenation intact.

    Returns ``content`` unchanged if no block exists (caller guards).
    """
    span = find_archive_override_block(content, "orfs")
    if not span:
        return content
    start, end = span
    block = content[start:end]

    var = _find_commit_var_in_block(block)
    if var is None:
        # Already at the target commit: the digest fields describe the same
        # tarball, so skip the download entirely.
        if _block_pins_commit(block, orfs_commit):
            print("  orfs already at target commit; skipping re-hash")
            return content
        # Literal shape: rewrite urls/strip_prefix, then the digest.
        if re.search(r'integrity\s*=\s*"', block):
            integrity = fetch_integrity_fn(github_archive_url(ORFS_REPO, orfs_commit))
            return update_archive_override(
                content, "orfs", ORFS_REPO, orfs_commit, integrity
            )
        block = re.sub(
            r'(urls\s*=\s*\[\s*")[^"]*(")',
            rf"\g<1>{github_archive_url(ORFS_REPO, orfs_commit)}\2",
            block,
            count=1,
        )
        block = re.sub(
            r'(strip_prefix\s*=\s*")[^"]*(")',
            rf"\g<1>{github_archive_strip_prefix(ORFS_REPO, orfs_commit)}\2",
            block,
            count=1,
        )
        block = _update_block_digest(
            block, ORFS_REPO, orfs_commit, fetch_integrity_fn, fetch_sha256_hex_fn
        )
        return content[:start] + block + content[end:]

    # Variable shape: both fields must reference the variable — a mixed
    # shape (one field a stale literal) would silently half-update.
    for field in ("strip_prefix", "urls"):
        _expect(
            re.search(
                field + r"\s*=[^,\n]*?\+\s*" + re.escape(var) + r"\b",
                block,
            ),
            f'{field} referencing {var} in archive_override(module_name = "orfs")',
            ignore_errors,
        )
    m_var = re.search(
        r"^" + re.escape(var) + r'\s*=\s*"([^"]*)"', content, flags=re.MULTILINE
    )
    if m_var and m_var.group(1) == orfs_commit:
        print("  orfs already at target commit; skipping re-hash")
        return content
    block = _update_block_digest(
        block, ORFS_REPO, orfs_commit, fetch_integrity_fn, fetch_sha256_hex_fn
    )
    content = content[:start] + block + content[end:]
    # Rewrite the top-level assignment.  Anchored at line start:
    # ``BAZEL_ORFS_COMMIT = "`` contains ``ORFS_COMMIT = "`` as a substring,
    # and an unanchored sub would clobber the just-bumped bazel-orfs pin.
    return re.sub(
        r"^(" + re.escape(var) + r'\s*=\s*")[^"]*(")',
        rf"\g<1>{orfs_commit}\2",
        content,
        flags=re.MULTILINE,
    )


# The digest check that always follows the download in a generated submodule
# patch_cmd.  Everything before it is the fetch step, which a consumer may
# have redirected at a mirror.
_SUBMODULE_FETCH_END = " && echo '"

# The staging filename the generator picks, which carries the submodule sha.
# Read the sha from here rather than from the download URL: a mirrored fetch
# names its object however the mirror does, but the staging file is ours.
_SUBMODULE_STAGEFILE_RE = re.compile(
    r"\.openroad-submodule-.+?-([0-9a-f]{40})\.tar\.gz"
)


def _is_submodule_fetch_cmd(cmd):
    """Is this patch_cmd a generated "fetch, verify, extract a submodule" line?

    Keyed on the verify-and-extract tail the generator always writes, so a
    fetch step pointed at a mirror still reads as generated.
    """
    return (
        _SUBMODULE_FETCH_END in cmd
        and "| sha256sum -c - &&" in cmd
        and "--strip-components=1 -C " in cmd
    )


def _submodule_fetch_step(cmd):
    """The download portion of a generated submodule patch_cmd, or None."""
    if not _is_submodule_fetch_cmd(cmd):
        return None
    return cmd[: cmd.index(_SUBMODULE_FETCH_END)]


def _is_default_submodule_fetch(fetch):
    """Is this the curl-from-GitHub fetch step the generator writes by default?"""
    return fetch.startswith("curl -sSfL") and "https://github.com/" in fetch


def _openroad_submodule_patch_cmd(
    path, github_repo, sha, sha256_hex, fetch_template=None
):
    """Render one patch_cmds fetch-extract line for an OpenROAD submodule.

    Format: download to a SHA-suffixed staging file *inside the repo's own
    workdir* (not /tmp — many hosts mount /tmp as tmpfs and the OpenROAD
    submodule tarballs are large enough to matter), verify with sha256sum,
    untar with --strip-components=1 into the empty submodule directory the
    parent archive left behind, clean up.  --retry absorbs transient
    network blips (mirrors the qt-bazel xcb-util-cursor pattern in
    //MODULE.bazel).

    The flags stay within reach of an old host curl: patch_cmds run in the
    host shell, so anything newer than the distro's curl turns a fetch into
    a hard repository-rule failure.  --retry-connrefused is curl 7.52
    (2016); --retry-all-errors would be 7.71 (2020) and breaks e.g. RHEL 8's
    7.61.

    ``fetch_template`` replaces the default curl-from-GitHub download with a
    consumer's mirror fetch, with ``{sha}`` and ``{sha256}`` substituted.  The
    verify, extract and cleanup steps stay generated either way, so the digest
    is still checked no matter where the bytes came from.
    """
    stagefile = f".openroad-submodule-{path.replace('/', '-')}-{sha}.tar.gz"
    if fetch_template:
        fetch = fetch_template.replace("{sha}", sha).replace("{sha256}", sha256_hex)
    else:
        archive_url = f"https://github.com/{github_repo}/archive/{sha}.tar.gz"
        fetch = (
            f"curl -sSfL --retry 5 --retry-connrefused --retry-delay 5 "
            f"-o {stagefile} {archive_url}"
        )
    return (
        f"{fetch} && "
        f"echo '{sha256_hex}  {stagefile}' | sha256sum -c - && "
        f"tar xzf {stagefile} --strip-components=1 -C {path} && "
        f"rm {stagefile}"
    )


def _format_openroad_archive_override(
    openroad_commit,
    parent_integrity,
    submodule_info,
    patches,
    patch_cmds_suffix="",
    submodule_patch_cmds=None,
    trailing_comments=None,
    mirror_url_templates=None,
    submodule_fetch_templates=None,
):
    """Render the openroad archive_override block as Starlark source text.

    ``submodule_info``: list of ``(path, github_repo, sha, sha256_hex)``.
    ``patches``: list of patch label strings (empty -> no patches/patch_strip).
    ``patch_cmds_suffix``: optional string like ``+ OPENROAD_CUSTOM_PATCH_CMDS`` to append.
    ``submodule_patch_cmds``: optional list of ``(label, cmd_string)`` for base64-encoded patches.
    ``mirror_url_templates``: optional mirror URLs for the parent archive,
    listed ahead of the GitHub URL; ``{commit}`` is substituted.
    ``submodule_fetch_templates``: optional ``path -> fetch step`` overrides,
    see :func:`_openroad_submodule_patch_cmd`.

    Attribute order matches buildifier convention: ``module_name`` first,
    rest alphabetical.  fix_lint will re-format anyway, but landing close
    to the final shape keeps diffs small.
    """
    parent_url = f"https://github.com/{OPENROAD_REPO}/archive/{openroad_commit}.tar.gz"
    parent_strip = f"OpenROAD-{openroad_commit}"
    submodule_patch_cmds = submodule_patch_cmds or []
    trailing_comments = trailing_comments or []
    submodule_fetch_templates = submodule_fetch_templates or {}
    parent_urls = [
        t.replace("{commit}", openroad_commit) for t in mirror_url_templates or []
    ]
    parent_urls.append(parent_url)

    lines = [
        "archive_override(",
        '    module_name = "openroad",',
        f'    integrity = "{parent_integrity}",',
        "    # GitHub /archive/<sha>.tar.gz tarballs don't carry submodules,",
        "    # so vendor src/sta (OpenSTA) and third-party/abc from their own",
        "    # GitHub auto-archives at the SHAs OpenROAD's .gitmodules pins",
        "    # to.  sha256sum -c verifies each tarball since patch_cmds bytes",
        "    # aren't covered by archive_override's integrity.  Regenerated",
        "    # by bump.py on every commit bump; do not edit by hand.",
        "    patch_cmds = [",
    ]
    for path, github_repo, sha, sha256_hex in submodule_info:
        cmd = _openroad_submodule_patch_cmd(
            path,
            github_repo,
            sha,
            sha256_hex,
            submodule_fetch_templates.get(path),
        )
        lines.append(f"        {cmd!r},")
    # OpenROAD aliases @slang -> @sv-lang//:libsvlang via
    # new_local_repository(name="slang", path="bazel"), and Bazel resolves
    # `path` against the *consumer* workspace root.  Consumers don't have
    # OpenROAD's bazel/ directory there, so the alias fetch fails the moment
    # anything references @slang.  Rewrite the lone reference in slang-elab
    # to use @sv-lang directly so the alias is never triggered.
    lines.append(
        r"""        "find . -name BUILD -exec sed -i 's|\"@slang\"|\"@sv-lang//:libsvlang\"|g' {} +","""
    )
    lines.append(
        r"""        "sed -i 's|defines = \\[|copts = [\"-include\", \"fmt/format.h\"],\\n    defines = [|' src/syn/src/elab/BUILD third-party/slang-elab/src/BUILD","""
    )

    for comments, label, cmd in submodule_patch_cmds:
        for c in comments:
            lines.append(f"        {c}")
        lines.append(f"        # Extracted from {label}")
        lines.append(f"        {cmd},")

    if patch_cmds_suffix:
        lines.append(f"    ] {patch_cmds_suffix},")
    else:
        lines.append("    ],")

    if patches:
        lines.append("    patch_strip = 1,")
        lines.append("    patches = [")
        for comments, p in patches:
            for c in comments:
                lines.append(f"        {c}")
            lines.append(f'        "{p}",')
        lines.append("    ],")
    for c in trailing_comments:
        lines.append(f"    {c}")
    lines.append(f'    strip_prefix = "{parent_strip}",')
    if len(parent_urls) == 1:
        lines.append(f'    urls = ["{parent_urls[0]}"],')
    else:
        lines.append("    urls = [")
        for url in parent_urls:
            lines.append(f'        "{url}",')
        lines.append("    ],")
    lines.append(")")
    return "\n".join(lines)


def validate_bazel_patch(patch_path, patch_content):
    """Validate that a patch conforms to Bazel's strict builtin patcher requirements."""
    in_hunk = False
    old_expected = 0
    new_expected = 0
    old_actual = 0
    new_actual = 0
    hunk_header = ""
    line_num = 0

    for line in patch_content.splitlines():
        line_num += 1
        if line.startswith("@@ "):
            if in_hunk:
                if old_expected != old_actual or new_expected != new_actual:
                    raise BumpError(
                        f"Patch {patch_path} has invalid hunk header '{hunk_header}': expected ({old_expected},{new_expected}) but found ({old_actual},{new_actual}). Bazel's strict patcher will fail."
                    )

            in_hunk = True
            hunk_header = line.strip()
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                old_expected = int(m.group(2)) if m.group(2) else 1
                new_expected = int(m.group(4)) if m.group(4) else 1
                old_actual = 0
                new_actual = 0
            else:
                in_hunk = False
        elif in_hunk:
            if line.startswith("+"):
                new_actual += 1
            elif line.startswith("-"):
                old_actual += 1
            elif line.startswith(" "):
                old_actual += 1
                new_actual += 1
            elif line == "":
                raise BumpError(
                    f"Patch {patch_path} has an empty context line at line {line_num} ('{hunk_header}'). Bazel's strict patcher requires a leading space for empty context lines."
                )
            elif line.startswith("\\ No newline at end of file"):
                pass
            else:
                if old_expected != old_actual or new_expected != new_actual:
                    raise BumpError(
                        f"Patch {patch_path} has invalid hunk header '{hunk_header}': expected ({old_expected},{new_expected}) but found ({old_actual},{new_actual}). Bazel's strict patcher will fail."
                    )
                in_hunk = False

    if in_hunk:
        if old_expected != old_actual or new_expected != new_actual:
            raise BumpError(
                f"Patch {patch_path} has invalid hunk header '{hunk_header}': expected ({old_expected},{new_expected}) but found ({old_actual},{new_actual}). Bazel's strict patcher will fail."
            )


def _extract_patches(block):
    """Return the list of patch labels found inside a Starlark block.

    Matches ``"//<path>:foo.patch"`` and ``"//:foo.patch"`` style labels —
    the only shapes used by bazel-orfs's openroad overrides today.
    """
    return re.findall(r'"(//[^"]*\.patch)"', block)


def _extract_patch_cmds(block):
    """Return the list of patch_cmds strings found inside a Starlark block."""
    m = re.search(r"patch_cmds\s*=\s*\[(.*?)\]", block, re.DOTALL)
    if not m:
        return []
    return [match.group(1) for match in re.finditer(r'"((?:\\.|[^"\\])*)"', m.group(1))]


def _is_custom_patch_cmd(cmd):
    """Return True if a patch_cmd was manually added (not bump.py generated)."""
    if cmd.startswith("curl -sSfL") and "tar xzf" in cmd:
        return False
    if _is_submodule_fetch_cmd(cmd):
        return False
    if (
        's|\\"@slang\\"|\\"@sv-lang//:libsvlang\\"|' in cmd
        or 's|"@slang"|"@sv-lang//:libsvlang"|' in cmd
    ):
        return False
    if cmd.startswith("echo ") and "| base64 -d | patch " in cmd:
        return False
    if "fmt/format.h" in cmd and "defines = [" in cmd:
        return False
    return True


def _parse_openroad_parent_commit(block):
    """Return the parent commit an openroad archive_override is pinned to."""
    m = re.search(r'strip_prefix\s*=\s*"OpenROAD-([^"]+)"', block)
    return m.group(1) if m else None


def _parse_submodule_digests(block):
    """Map submodule path -> (sha, sha256_hex) from generated patch_cmds.

    Reads back what :func:`_openroad_submodule_patch_cmd` wrote.  Lets a
    re-bump at an unchanged parent commit reuse the digests instead of
    re-downloading every submodule tarball just to hash it to the same
    value: the submodule shas are a function of the parent commit.
    """
    digests = {}
    for cmd in _extract_patch_cmds(block):
        m_sha = _SUBMODULE_STAGEFILE_RE.search(cmd) or re.search(
            r"/archive/([^/\s]+?)\.tar\.gz", cmd
        )
        m_hex = re.search(r"echo '([0-9a-f]{64})  ", cmd)
        m_path = re.search(r"--strip-components=1 -C (\S+) ", cmd)
        if m_sha and m_hex and m_path:
            digests[m_path.group(1)] = (m_sha.group(1), m_hex.group(1))
    return digests


def _parse_submodule_mirror_fetches(block):
    """Map submodule path -> fetch-step template for redirected fetches.

    GitHub's codeload cache has been observed serving HTTP 400 for the
    tar.gz-by-sha key of individual commits, which leaves a consumer no
    option but to fetch that submodule from a mirror.  Capture such a fetch
    step with the sha and digest reduced to ``{sha}`` / ``{sha256}``
    placeholders, so regenerating the block re-renders it at the new commit
    instead of dropping it.
    """
    fetches = {}
    for cmd in _extract_patch_cmds(block):
        fetch = _submodule_fetch_step(cmd)
        if fetch is None or _is_default_submodule_fetch(fetch):
            continue
        m_path = re.search(r"--strip-components=1 -C (\S+) ", cmd)
        m_hex = re.search(r"echo '([0-9a-f]{64})  ", cmd)
        m_sha = _SUBMODULE_STAGEFILE_RE.search(cmd)
        if not (m_path and m_hex and m_sha):
            continue
        template = fetch.replace(m_sha.group(1), "{sha}")
        template = template.replace(m_hex.group(1), "{sha256}")
        fetches[m_path.group(1)] = template
    return fetches


def _parse_mirror_urls(block, commit):
    """The non-GitHub entries of ``urls = [...]``, as templates.

    ``commit`` (the commit the block is currently pinned to) is reduced to a
    ``{commit}`` placeholder so a mirror URL naming the archive by sha
    re-renders at the new commit.
    """
    m = re.search(r"urls\s*=\s*\[(.*?)\]", block, re.DOTALL)
    if not m:
        return []
    templates = []
    for url in re.findall(r'"([^"]*)"', m.group(1)):
        if _GITHUB_ARCHIVE_URL_RE.fullmatch(url):
            continue
        templates.append(url.replace(commit, "{commit}") if commit else url)
    return templates


def _resolve_openroad_archives(
    openroad_commit,
    fetch_integrity_fn,
    fetch_sha256_hex_fn,
    fetch_submodule_sha_fn,
    known_digests=None,
):
    """Hash the parent archive and every submodule archive, concurrently.

    Four multi-MB tarballs get downloaded purely to be hashed; doing them
    serially dominated the wall clock of a bump.  Each submodule's sha
    lookup and tarball hash stay sequential with respect to each other
    (the sha names the tarball), but the submodules run alongside one
    another and alongside the parent.

    ``known_digests`` maps submodule path -> (sha, sha256_hex) as already
    recorded in the block being regenerated.  A submodule whose sha the new
    parent commit leaves unchanged keeps its recorded digest: re-hashing it
    would download a tarball to arrive at the digest we already hold, and
    GitHub's archives are not byte-stable, so the value can come back
    *different* for identical content.  A digest that moves without its sha
    moving invalidates any mirror keyed by digest, and stops a mismatch from
    meaning what it should.
    """
    parent_url = github_archive_url(OPENROAD_REPO, openroad_commit)
    known_digests = known_digests or {}

    def resolve_submodule(path, github_repo):
        sub_sha = fetch_submodule_sha_fn(OPENROAD_REPO, openroad_commit, path)
        known = known_digests.get(path)
        if known and known[0] == sub_sha:
            return (path, github_repo, sub_sha, known[1])
        sub_url = f"https://github.com/{github_repo}/archive/{sub_sha}.tar.gz"
        return (path, github_repo, sub_sha, fetch_sha256_hex_fn(sub_url))

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1 + len(OPENROAD_SUBMODULES)
    ) as pool:
        parent = pool.submit(fetch_integrity_fn, parent_url)
        subs = [
            pool.submit(resolve_submodule, path, github_repo)
            for path, github_repo in OPENROAD_SUBMODULES
        ]
        return parent.result(), [f.result() for f in subs]


def update_openroad_archive_override(
    content,
    openroad_commit,
    fetch_integrity_fn=compute_integrity,
    fetch_sha256_hex_fn=compute_sha256_hex,
    fetch_submodule_sha_fn=fetch_submodule_sha,
    fetch_commit_date_fn=fetch_commit_date,
    workspace_dir=None,
):
    """Regenerate the ``archive_override(module_name = "openroad")`` block.

    openroad is pinned via archive_override rather than git_override +
    init_submodules, which has a long-standing reliability bug (interrupted
    fetches leave empty submodule directories that Bazel then reuses).
    GitHub's auto-archive of the parent doesn't include submodules, so this
    regenerates patch_cmds that curl each submodule's own
    /archive/<sha>.tar.gz and extract it in place.

    Returns ``content`` unchanged if there is no such block — a legacy
    git_override(openroad) is outside the supported window and is reported
    by the caller's ``_expect``.  Idempotent: invoking twice with the same
    commit produces identical output.
    """
    span = find_archive_override_block(content, "openroad")
    if span is None:
        return content
    start, end = span
    old_block = content[start:end]

    m_suffix = re.search(
        r"patch_cmds\s*=\s*\[.*?\](\s*\+\s*[A-Za-z0-9_]+)?,", old_block, re.DOTALL
    )
    patch_cmds_suffix = ""
    if m_suffix and m_suffix.group(1):
        patch_cmds_suffix = m_suffix.group(1).strip()

    old_patch_cmds = _extract_patch_cmds(old_block)
    custom_cmds = [cmd for cmd in old_patch_cmds if _is_custom_patch_cmd(cmd)]
    if custom_cmds:
        raise BumpError(
            "Manual submodule patch_cmds found in archive_override(openroad). "
            "bump.py now automatically base64 encodes submodule patches. "
            "Please move these patches back into the standard `patches = [...]` list "
            "and remove any manual patch_cmds."
        )

    generated_comments = {
        "# GitHub /archive/<sha>.tar.gz tarballs don't carry submodules,",
        "# so vendor src/sta (OpenSTA) and third-party/abc from their own",
        "# GitHub auto-archives at the SHAs OpenROAD's .gitmodules pins",
        "# to.  sha256sum -c verifies each tarball since patch_cmds bytes",
        "# aren't covered by archive_override's integrity.  Regenerated",
        "# by bump.py on every commit bump; do not edit by hand.",
        "# by bump.py on every commit bump.",
    }
    patches_with_comments = []
    trailing_comments = []
    current_comments = []

    for line in old_block.splitlines():
        line_stripped = line.strip()
        if (
            line_stripped.startswith("#")
            and line_stripped not in generated_comments
            and not line_stripped.startswith("# Extracted from")
        ):
            current_comments.append(line_stripped)
        elif '"//' in line_stripped and ".patch" in line_stripped:
            matches = re.findall(r'"(//[^"]*\.patch)"', line_stripped)
            if matches:
                for idx, match in enumerate(matches):
                    if idx == 0:
                        patches_with_comments.append((current_comments, match))
                        current_comments = []
                    else:
                        patches_with_comments.append(([], match))
        elif line_stripped == ")" or line_stripped == "],":
            trailing_comments.extend(current_comments)
            current_comments = []

    top_patches = []
    submodule_patch_cmds = []

    if workspace_dir:
        for comments, p in patches_with_comments:
            # e.g. "//orfs-patches:foo.patch" -> "orfs-patches/foo.patch"
            if p.startswith("//"):
                parts = p[2:].split(":")
                rel_path = f"{parts[0]}/{parts[1]}" if parts[0] else parts[1]
                full_path = os.path.join(workspace_dir, rel_path)
            else:
                full_path = os.path.join(workspace_dir, p)

            if not os.path.exists(full_path):
                top_patches.append((comments, p))
                continue

            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                patch_content = f.read()

            validate_bazel_patch(full_path, patch_content)

            touches_submodule = False
            for sub_path, _ in OPENROAD_SUBMODULES:
                # E.g. --- a/src/sta/ or +++ b/src/sta/
                if re.search(
                    r"^[+-]{3} [ab]/" + re.escape(sub_path) + r"/",
                    patch_content,
                    re.MULTILINE,
                ):
                    touches_submodule = True
                    break

            if touches_submodule:
                normalized = patch_content.replace("\r\n", "\n").replace("\r", "\n")
                if normalized and not normalized.endswith("\n"):
                    normalized += "\n"
                b64 = base64.b64encode(normalized.encode("utf-8")).decode("ascii")
                cmd = f"echo {b64} | base64 -d | patch -p1 || (echo 'ERROR: Patch {p} failed to apply to submodule. Please rebase the source of truth patch at {p}.' && exit 1)"
                submodule_patch_cmds.append((comments, p, f'"{cmd}"'))
            else:
                top_patches.append((comments, p))
    else:
        top_patches = patches_with_comments

    # Already pinned to this commit?  Every digest in the block describes a
    # tarball we would re-download only to hash it to the same value, so
    # reuse them and regenerate the block (patches may still have changed).
    parent_integrity = None
    submodule_info = []
    if _parse_openroad_parent_commit(old_block) == openroad_commit:
        digests = _parse_submodule_digests(old_block)
        m_integrity = re.search(r'integrity\s*=\s*"([^"]*)"', old_block)
        if m_integrity and all(path in digests for path, _ in OPENROAD_SUBMODULES):
            parent_integrity = m_integrity.group(1)
            submodule_info = [
                (path, github_repo) + digests[path]
                for path, github_repo in OPENROAD_SUBMODULES
            ]
            print("  openroad already at target commit; skipping re-hash")

    if parent_integrity is None:
        parent_integrity, submodule_info = _resolve_openroad_archives(
            openroad_commit,
            fetch_integrity_fn,
            fetch_sha256_hex_fn,
            fetch_submodule_sha_fn,
            _parse_submodule_digests(old_block),
        )

    # Mirrors a consumer added are configuration, not hand-edits to undo:
    # carry them over at the new commit rather than regenerating them away.
    new_block = _format_openroad_archive_override(
        openroad_commit,
        parent_integrity,
        submodule_info,
        top_patches,
        patch_cmds_suffix,
        submodule_patch_cmds,
        trailing_comments,
        _parse_mirror_urls(old_block, _parse_openroad_parent_commit(old_block)),
        _parse_submodule_mirror_fetches(old_block),
    )
    return content[:start] + new_block + content[end:]


# Non-BCR deps that downstream projects need overrides for.
# These are read from bazel-orfs's own MODULE.bazel and injected
# into downstream projects during bump.
NON_BCR_DEPS = [
    "orfs",
    "openroad",
    "qt-bazel",
]


def read_bazel_orfs_overrides(bazel_orfs_module_path):
    """Read git_override blocks from bazel-orfs's MODULE.bazel.

    Returns dict of module_name -> (bazel_dep line, git_override block text).
    """
    with open(bazel_orfs_module_path) as f:
        text = f.read()

    overrides = {}
    for name in NON_BCR_DEPS:
        span = find_git_override_block(text, name)
        if span:
            overrides[name] = text[span[0] : span[1]]
    return overrides


BAZEL_ORFS_PATCHES_DIR = "orfs-patches"


def copy_patches(bazel_orfs_dir, workspace_dir):
    """Copy bazel-orfs patches into the downstream project.

    Creates bazel-orfs-patches/ with a BUILD.bazel that exports all .patch files.
    Returns the label prefix for referencing these patches.
    """
    import shutil

    src_patches = os.path.join(bazel_orfs_dir, "patches")
    dst_dir = os.path.join(workspace_dir, BAZEL_ORFS_PATCHES_DIR)
    if not os.path.isdir(src_patches):
        return

    os.makedirs(dst_dir, exist_ok=True)
    for f in os.listdir(src_patches):
        if f.endswith(".patch"):
            shutil.copy2(os.path.join(src_patches, f), dst_dir)

    # Also copy root-level patches referenced as //:foo.patch
    for f in os.listdir(bazel_orfs_dir):
        if f.endswith(".patch"):
            shutil.copy2(os.path.join(bazel_orfs_dir, f), dst_dir)

    build_path = os.path.join(dst_dir, "BUILD.bazel")
    if not os.path.exists(build_path):
        with open(build_path, "w") as fh:
            fh.write('exports_files(glob(["*.patch"]))\n')


def rewrite_patch_labels(override_block):
    """Rewrite patch labels to reference the local bazel-orfs-patches/ dir.

    In bazel-orfs's MODULE.bazel, patches reference:
        //patches:foo.patch  or  //:foo.patch
    In downstream projects, these become:
        //bazel-orfs-patches:foo.patch
    """

    def rewrite(m):
        label = m.group(1)
        # Extract just the filename
        filename = label.split(":")[-1]
        return f'"//{BAZEL_ORFS_PATCHES_DIR}:{filename}"'

    override_block = re.sub(
        r'"(//(?:patches|)[^"]*\.patch)"',
        rewrite,
        override_block,
    )
    return override_block


def inject_non_bcr_deps(content, bazel_orfs_dir):
    """Inject git_override blocks for non-BCR deps that downstream projects need.

    Reads the override blocks from bazel-orfs's own MODULE.bazel and
    injects them (with rewritten patch labels) into the downstream content.
    """
    module_path = os.path.join(bazel_orfs_dir, "MODULE.bazel")
    if not os.path.exists(module_path):
        return content

    overrides = read_bazel_orfs_overrides(module_path)
    missing = [name for name in NON_BCR_DEPS if not has_bazel_dep(content, name)]
    if not missing:
        return content

    # Find insertion point: after the bazel-orfs git_override
    span = find_git_override_block(content, "bazel-orfs")
    if not span:
        return content
    insert_pos = span[1]

    blocks = []
    for name in missing:
        if name in overrides:
            block = overrides[name]
            block = rewrite_patch_labels(block)
            # Strip inline comments but preserve structure
            lines = block.split("\n")
            lines = [l for l in lines if not l.strip().startswith("#")]
            block = "\n".join(lines)
            blocks.append(f'\nbazel_dep(name = "{name}")\n' + block)

    if blocks:
        return content[:insert_pos] + "\n" + "\n".join(blocks) + content[insert_pos:]
    return content


def fetch_json(url):
    """Fetch JSON from a URL."""
    req = urllib.request.Request(url)
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {github_token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_latest_commit(github_repo, branch):
    """Get the latest commit SHA from a GitHub repo."""
    url = f"https://api.github.com/repos/{github_repo}" f"/commits/{branch}"
    data = fetch_json(url)
    sha = data.get("sha")
    if not sha:
        raise RuntimeError(f"Failed to fetch commit from {github_repo}/{branch}")
    return sha


def fetch_latest_github_release(github_repo):
    """Get the latest release tag from a GitHub repo."""
    url = f"https://api.github.com/repos/{github_repo}/releases/latest"
    data = fetch_json(url)
    tag = data.get("tag_name")
    if not tag:
        raise RuntimeError(f"No releases found for {github_repo}")
    return tag


def fetch_tag_commit(github_repo, tag):
    """Get the commit SHA that a tag points to."""
    url = f"https://api.github.com/repos/{github_repo}/git/ref/tags/{tag}"
    data = fetch_json(url)
    obj = data.get("object", {})
    # If it's an annotated tag, dereference to the commit
    if obj.get("type") == "tag":
        tag_url = obj["url"]
        tag_data = fetch_json(tag_url)
        return tag_data["object"]["sha"]
    return obj.get("sha", "")


def _read_bazel_dep_version(content, module_name):
    """Return the version string of a ``bazel_dep(name=..., version=...)`` or None."""
    m = re.search(
        r'bazel_dep\s*\([^)]*name\s*=\s*"'
        + re.escape(module_name)
        + r'"[^)]*version\s*=\s*"([^"]+)"',
        content,
        re.DOTALL,
    )
    if m:
        return m.group(1)
    return None


def _read_single_version_override(content, module_name):
    """Return the version pinned by ``single_version_override(...)`` or None.

    Identifies blocks by ``single_version_override(`` at the start of a line
    and the matching ``)`` at the start of a line (Bazel/Buildifier formatting
    convention).  This is robust against parens embedded in multi-line
    ``patch_cmds`` triple-quoted strings, which would defeat a naive
    paren-balanced regex.
    """
    lines = content.split("\n")
    i = 0
    while i < len(lines):
        if re.match(r"^single_version_override\s*\(", lines[i]):
            j = i + 1
            while j < len(lines) and not lines[j].startswith(")"):
                j += 1
            block = "\n".join(lines[i : j + 1])
            if f'module_name = "{module_name}"' in block:
                m = re.search(r'\bversion\s*=\s*"([^"]+)"', block)
                if m:
                    return m.group(1)
            i = j + 1
        else:
            i += 1
    return None


def _yosys_major_minor(version):
    """Reduce a yosys version like '0.62.bcr.2' or '0.65' to '0.62' / '0.65'."""
    m = re.match(r"(\d+\.\d+)", version)
    return m.group(1) if m else None


def check_yosys_abc_pair(content):
    """Return (ok, message). Empty message on success.

    Validates the yosys/abc pairing in a downstream MODULE.bazel:
      * If neither is declared, returns ok.
      * If only one is declared, returns ok with a note.
      * If both are declared and match YOSYS_ABC_PAIRS, returns ok.
      * Otherwise returns (False, hint).
    """
    yosys_version = _read_bazel_dep_version(content, "yosys")
    abc_version = _read_single_version_override(
        content, "abc"
    ) or _read_bazel_dep_version(content, "abc")

    if yosys_version is None and abc_version is None:
        return True, ""

    if yosys_version is None or abc_version is None:
        return True, (
            "yosys-abc lockstep: only one of yosys/abc is declared; "
            "skipping pairing check."
        )

    series = _yosys_major_minor(yosys_version)
    expected_abc = YOSYS_ABC_PAIRS.get(series)
    if expected_abc is None:
        return False, (
            f"yosys-abc lockstep: no known abc pairing for yosys {yosys_version}. "
            f"Add an entry to YOSYS_ABC_PAIRS in bazel-orfs/bump.py "
            f"(see https://github.com/YosysHQ/yosys/tree/v{series}/abc "
            f"for the abc submodule SHA shipped with this yosys)."
        )
    if abc_version != expected_abc:
        return False, (
            f"yosys-abc lockstep: yosys {yosys_version} expects abc "
            f"{expected_abc!r}, but MODULE.bazel pins abc {abc_version!r}. "
            f"Update the abc pin to match, or change yosys."
        )
    return True, ""


# Source of truth for EDA tool versions: ORFS's tools/ submodules at master.
# The bumper reads each submodule's pinned sha at the just-bumped ORFS commit
# and applies it to the consumer's git_override blocks.  yosys is the odd
# one out — it ships on BCR, so we resolve ORFS's tools/yosys sha to a BCR
# version string and rewrite the ``bazel_dep`` instead of writing a
# ``git_override``.  See ``bump_yosys_bcr``.
ORFS_REPO = "The-OpenROAD-Project/OpenROAD-flow-scripts"
ORFS_TOOLS = {
    # tools/ subdir name -> (MODULE.bazel module name, upstream repo for --head)
    "OpenROAD": ("openroad", "The-OpenROAD-Project/OpenROAD"),
}

# OpenROAD is pinned via ``archive_override`` (GitHub /archive/<sha>.tar.gz)
# rather than ``git_override`` because git_repository + init_submodules isn't
# atomic: an interrupted fetch can leave the on-disk external repo with empty
# submodule directories ("BUILD file not found in directory 'src/sta'"), and
# Bazel reuses that broken state on subsequent builds.  GitHub's auto-archive
# of the parent doesn't carry submodules, so the missing pieces are vendored
# via ``patch_cmds`` that curl each submodule's own GitHub auto-archive and
# extract it in place.  Bazel docs recommend http_archive over git_repository
# for exactly this reliability reason.
OPENROAD_REPO = "The-OpenROAD-Project/OpenROAD"
OPENROAD_SUBMODULES = [
    # (in-repo path,            github repo)
    ("src/sta", "The-OpenROAD-Project/OpenSTA"),
    ("third-party/abc", "The-OpenROAD-Project/abc"),
    ("third-party/slang-elab", "povik/yosys-slang"),
]

# yosys is consumed from the Bazel Central Registry.  ORFS's tools/yosys pins
# a specific master commit (often between tagged releases), so we read the
# ``YOSYS_VER`` line from yosys/Makefile at that commit to learn the (M, m)
# release ORFS expects, then pick the highest BCR variant with base <= (M, m).
YOSYS_REPO = "YosysHQ/yosys"
YOSYS_BCR_MODULE = "yosys"
BCR_METADATA_URL = (
    "https://raw.githubusercontent.com/bazelbuild/bazel-central-registry/"
    "main/modules/{module}/metadata.json"
)


def fetch_orfs_tool_sha(orfs_commit, tool):
    """Submodule sha of ORFS/tools/<tool> at a specific ORFS commit.

    Pinning the ``?ref=<commit>`` matters: an unpinned query would silently
    drift if ORFS master moved between our ORFS bump and the tools/ reads.
    """
    url = (
        f"https://api.github.com/repos/{ORFS_REPO}/contents/tools/{tool}"
        f"?ref={orfs_commit}"
    )
    data = fetch_json(url)
    if data.get("type") != "submodule":
        raise RuntimeError(
            f"tools/{tool} is not a submodule at {orfs_commit} (got {data.get('type')!r})"
        )
    return data["sha"]


def fetch_yosys_makefile_version(sha):
    """Read yosys's ``(major, minor)`` version at a commit sha.

    Yosys carried a literal ``YOSYS_VER := M.m`` line in its top-level
    Makefile until the CMake migration deleted that file; since then the
    numbers live in ``cmake/YosysVersionData.cmake`` as
    ``set(YOSYS_VERSION_MAJOR M)`` / ``set(YOSYS_VERSION_MINOR m)``.
    ORFS pins tools/yosys to master commits that aren't always tagged, so
    reading the version file at the pinned sha is the only reliable way to
    learn which BCR release ORFS expects.  Returns ``(major, minor)``.
    """
    url = f"https://api.github.com/repos/{YOSYS_REPO}/contents/Makefile?ref={sha}"
    try:
        data = fetch_json(url)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        url = (
            f"https://api.github.com/repos/{YOSYS_REPO}/contents/"
            f"cmake/YosysVersionData.cmake?ref={sha}"
        )
        data = fetch_json(url)
        text = base64.b64decode(data["content"]).decode()
        major = re.search(r"set\(YOSYS_VERSION_MAJOR\s+(\d+)\)", text)
        minor = re.search(r"set\(YOSYS_VERSION_MINOR\s+(\d+)\)", text)
        if not (major and minor):
            raise RuntimeError(
                f"YOSYS_VERSION_MAJOR/MINOR not found in {YOSYS_REPO} "
                f"cmake/YosysVersionData.cmake at {sha[:12]}"
            )
        return (int(major.group(1)), int(minor.group(1)))
    text = base64.b64decode(data["content"]).decode()
    m = re.search(r"^\s*YOSYS_VER\s*:=\s*(\d+)\.(\d+)", text, re.MULTILINE)
    if not m:
        raise RuntimeError(
            f"YOSYS_VER not found in {YOSYS_REPO} Makefile at {sha[:12]}"
        )
    return (int(m.group(1)), int(m.group(2)))


def fetch_bcr_versions(module_name):
    """List published BCR versions for a module from the public registry."""
    return fetch_json(BCR_METADATA_URL.format(module=module_name)).get("versions", [])


_BCR_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.bcr\.(\d+))?$")


def _bcr_version_key(v):
    """Sort key for BCR-style version strings like '0.62.bcr.2' / '0.63'."""
    m = _BCR_VERSION_RE.match(v)
    if not m:
        return (-1, -1, -1)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def pick_bcr_yosys_version(bcr_versions, orfs_yosys_version):
    """Highest BCR yosys version whose base ``(M, m)`` is <= ORFS's pin.

    BCR may publish a new yosys before ORFS bumps to it, or lag behind it.
    Capping by ORFS's ``YOSYS_VER`` keeps us inside the range ORFS tests.
    """
    target = orfs_yosys_version
    candidates = [
        (key, v)
        for v in bcr_versions
        for key in (_bcr_version_key(v),)
        if key != (-1, -1, -1) and (key[0], key[1]) <= target
    ]
    if not candidates:
        raise RuntimeError(
            f"No BCR yosys version <= ORFS tools/yosys {target[0]}.{target[1]}"
        )
    return max(candidates)[1]


def update_bazel_dep_version(content, module_name, new_version):
    """Rewrite ``version`` in ``bazel_dep(name="<module>", version="...")``.

    Touches the first such occurrence only; consumers carry exactly one
    bazel_dep per module name.  Returns content unchanged if not found.
    """
    pattern = (
        r'(bazel_dep\(\s*name\s*=\s*"'
        + re.escape(module_name)
        + r'"\s*,\s*version\s*=\s*")[^"]*(")'
    )
    return re.sub(pattern, rf"\g<1>{new_version}\2", content, count=1)


def bump(
    module_file,
    fetch_commit_fn=fetch_latest_commit,
    fetch_integrity_fn=compute_integrity,
    fetch_orfs_tool_sha_fn=fetch_orfs_tool_sha,
    fetch_yosys_makefile_version_fn=fetch_yosys_makefile_version,
    fetch_bcr_versions_fn=fetch_bcr_versions,
    fetch_sha256_hex_fn=compute_sha256_hex,
    fetch_submodule_sha_fn=fetch_submodule_sha,
    fetch_commit_date_fn=fetch_commit_date,
    workspace_dir=None,
    head_tools=None,
    ignore_errors=False,
    bazel_orfs_commit=None,
):
    """Main bump orchestrator.

    The openroad version comes from ORFS's tools/OpenROAD submodule at the
    just-bumped ORFS master HEAD and is applied to the archive_override.
    yosys is on BCR: its ORFS tools/yosys pin is read to find ORFS's
    expected ``YOSYS_VER`` (M.m), and we pick the highest BCR variant with
    base <= that, then rewrite the ``bazel_dep`` version.  ``head_tools``
    (set of tool names) forces individual tools to chase upstream HEAD
    instead — escape hatch for debugging against an older ORFS pin.

    Project-type matrix (for the bazel-orfs / orfs commits proper):
        Project      bazel-orfs  ORFS
        bazel-orfs   skip(self)  yes
        OpenROAD     yes         yes
        downstream   yes         yes

    (OpenROAD never bumps its own commit: the tools loop below only
    touches an ``openroad`` *bazel_dep*, which OpenROAD's own
    MODULE.bazel doesn't have.)
    """
    if head_tools is None:
        head_tools = set()

    with open(module_file) as f:
        content = f.read()

    project = detect_project(content)
    updated_modules = []

    # --- Locate bazel-orfs source (for reading overrides and copying patches) ---
    bazel_orfs_dir = os.path.dirname(os.path.abspath(__file__))

    # --- Update bazel-orfs commit (skip for bazel-orfs itself) ---
    if project != "bazel-orfs":
        # main() resolves this first, for the window gate; re-resolving here
        # would risk gating one commit and writing another.
        if bazel_orfs_commit is None:
            bazel_orfs_commit = fetch_commit_fn(
                "The-OpenROAD-Project/bazel-orfs", "main"
            )
        _expect(
            find_git_override_block(content, "bazel-orfs"),
            'git_override(module_name = "bazel-orfs")',
            ignore_errors,
        )
        content = update_git_override_commit(content, "bazel-orfs", bazel_orfs_commit)
        updated_modules.append(f"bazel-orfs -> {bazel_orfs_commit[:12]}")

        # Inject non-BCR deps (orfs, openroad, qt-bazel) with commits
        # pinned to the same versions bazel-orfs uses
        content = inject_non_bcr_deps(content, bazel_orfs_dir)
        if workspace_dir:
            copy_patches(bazel_orfs_dir, workspace_dir)

    # --- Update ORFS commit (skip for projects without ORFS) ---
    # Every consumer follows ORFS master — including OpenROAD, whose orfs
    # pin gates its bazel-orfs integration tests; the tool overrides
    # (openroad/yosys below) are then resolved at the new ORFS commit so
    # the whole stack moves coherently.  Dispatch on the override shape,
    # not the project type: archive_override (literal or commit-variable
    # form) vs git_override.
    orfs_commit = None
    if has_bazel_dep(content, "orfs"):
        orfs_commit = fetch_commit_fn(ORFS_REPO, "master")
        _expect(
            find_archive_override_block(content, "orfs"),
            'archive_override(module_name = "orfs")',
            ignore_errors,
        )
        content = update_orfs_archive_override(
            content,
            orfs_commit,
            fetch_integrity_fn=fetch_integrity_fn,
            fetch_sha256_hex_fn=fetch_sha256_hex_fn,
            ignore_errors=ignore_errors,
        )
        updated_modules.append(f"orfs -> {orfs_commit[:12]}")
    elif find_orfs_source_tag(content):
        # ORFS as an extension-created http_archive: the version is an
        # orfs.source() tag rather than an override, so that bazel-orfs
        # owns the patches for every root module.
        orfs_commit = fetch_commit_fn(ORFS_REPO, "master")
        content = update_orfs_source_tag(
            content,
            orfs_commit,
            fetch_integrity_fn=fetch_integrity_fn,
            ignore_errors=ignore_errors,
        )
        updated_modules.append(f"orfs -> {orfs_commit[:12]}")

    # --- Update qt-bazel commit ---
    if has_bazel_dep(content, "qt-bazel"):
        qt_commit = fetch_commit_fn("The-OpenROAD-Project/qt_bazel_prebuilts", "main")
        _expect(
            find_git_override_block(content, "qt-bazel"),
            'git_override(module_name = "qt-bazel")',
            ignore_errors,
        )
        content = update_git_override_commit(content, "qt-bazel", qt_commit)
        updated_modules.append(f"qt-bazel -> {qt_commit[:12]}")

    # --- Bump yosys to latest BCR version capped by ORFS tools/yosys ---
    if orfs_commit is not None and has_bazel_dep(content, YOSYS_BCR_MODULE):
        orfs_yosys_sha = fetch_orfs_tool_sha_fn(orfs_commit, "yosys")
        orfs_yosys_ver = fetch_yosys_makefile_version_fn(orfs_yosys_sha)
        bcr_versions = fetch_bcr_versions_fn(YOSYS_BCR_MODULE)
        bcr_version = pick_bcr_yosys_version(bcr_versions, orfs_yosys_ver)
        new_content = update_bazel_dep_version(content, YOSYS_BCR_MODULE, bcr_version)
        # has_bazel_dep matched.  If the rewrite changed nothing AND the
        # bazel_dep isn't already pinned to bcr_version, the version field
        # is in an unexpected shape (e.g. variable-bound).  Read the pin
        # via the parser rather than an exact-string match so extra
        # attributes (OpenROAD's ``dev_dependency = True``) don't turn a
        # correctly-pinned no-op into a spurious failure.
        already_pinned = (
            _read_bazel_dep_version(content, YOSYS_BCR_MODULE) == bcr_version
        )
        _expect(
            new_content != content or already_pinned,
            f'bazel_dep(name = "{YOSYS_BCR_MODULE}", version = "...")',
            ignore_errors,
        )
        content = new_content
        updated_modules.append(
            f"yosys -> {bcr_version} (BCR <= ORFS tools/yosys "
            f"{orfs_yosys_ver[0]}.{orfs_yosys_ver[1]})"
        )

    # --- Update openroad from ORFS tools/OpenROAD (or its own HEAD) ---
    if orfs_commit is not None:
        for tool, (module_name, upstream_repo) in ORFS_TOOLS.items():
            if module_name == "openroad" and not has_bazel_dep(content, "openroad"):
                continue
            if module_name in head_tools:
                # --head=openroad bypasses ORFS entirely.
                sha = fetch_commit_fn(upstream_repo, "master")
                source = f"HEAD of {upstream_repo}"
            else:
                sha = fetch_orfs_tool_sha_fn(orfs_commit, tool)
                source = f"ORFS tools/{tool}"

            if module_name == "openroad":
                # openroad is pinned via archive_override + submodule
                # patch_cmds rather than git_override (the latter's
                # init_submodules path has a non-atomic-fetch bug — see the
                # OPENROAD_REPO comment).  The block is regenerated in place.
                _expect(
                    find_archive_override_block(content, "openroad"),
                    'archive_override(module_name = "openroad")',
                    ignore_errors,
                )
                content = update_openroad_archive_override(
                    content,
                    sha,
                    fetch_integrity_fn=fetch_integrity_fn,
                    fetch_sha256_hex_fn=fetch_sha256_hex_fn,
                    fetch_submodule_sha_fn=fetch_submodule_sha_fn,
                    workspace_dir=workspace_dir,
                )
                updated_modules.append(f"{module_name} -> {sha[:12]} ({source})")
            else:
                _expect(
                    find_git_override_block(content, module_name),
                    f'git_override(module_name = "{module_name}")',
                    ignore_errors,
                )
                content = update_git_override_commit(content, module_name, sha)
                updated_modules.append(f"{module_name} -> {sha[:12]} ({source})")

    # --- Record the tree's dated anchor (bazel-orfs only) ---
    # The ORFS pin's commit date is what //:bump_compat_test measures COMPAT
    # markers against.  Recording it here keeps the cleanup policy on commit
    # dates: the anchor moves when the dependency stack moves, not with the
    # calendar, so a given tree always gets the same verdict.
    if project == "bazel-orfs" and workspace_dir and orfs_commit is not None:
        write_reference_date(
            workspace_dir, fetch_commit_date_fn(ORFS_REPO, orfs_commit)
        )

    # --- Validate yosys/abc lockstep (downstream MODULE.bazel) ---
    # In the bump path this is informational: BCR availability and yosys
    # release cadence don't always line up (e.g. yosys 0.63 ships without
    # a matching abc 0.63-yosyshq on BCR), and blocking the bumper on that
    # would be more disruptive than the lurking quality risk. CI gets the
    # hard check via //:bump_yosys_abc_test; consumers get it via the
    # `--check-yosys-abc` entrypoint.
    ok, msg = check_yosys_abc_pair(content)
    if not ok:
        sys.stderr.write("WARNING: " + msg + "\n")

    with open(module_file, "w") as f:
        f.write(content)

    # --- Summary ---
    print(f"Updated {module_file} ({project} project):")
    for entry in updated_modules:
        print(f"  {entry}")

    return content


def run_mod_tidy(workspace_dir):
    """Run ``bazelisk mod tidy`` to refresh MODULE.bazel.lock.

    The git_override commits rewritten by bump() invalidate the lockfile;
    `mod tidy` resolves the new graph and writes the updated lock (and
    tidies any stale use_repo entries while it's there).

    The MODULE.bazel rewrite already happened — if mod tidy fails (e.g.
    a patch no longer applies against a freshly-bumped commit), leave the
    rewritten file in place so the human can inspect, and exit with the
    subprocess's status. A Python traceback would just hide the real error
    that bazelisk already printed to stderr.
    """
    print("Running bazelisk mod tidy to update MODULE.bazel.lock...")
    result = subprocess.run(["bazelisk", "mod", "tidy"], cwd=workspace_dir)
    if result.returncode != 0:
        sys.exit(result.returncode)


_HEAD_TOOLS = {module_name for module_name, _ in ORFS_TOOLS.values()}


def main():
    parser = argparse.ArgumentParser(
        description="Bump bazel-orfs and dependency versions"
    )
    parser.add_argument(
        "--module-file",
        default=os.path.join(
            os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."),
            "MODULE.bazel",
        ),
        help="Path to MODULE.bazel",
    )
    parser.add_argument(
        "--head",
        action="append",
        default=[],
        choices=sorted(_HEAD_TOOLS),
        metavar="TOOL",
        help=(
            "Pin TOOL to its upstream HEAD instead of the ORFS-tools-pinned "
            "sha. Repeatable. Useful when debugging against a fix that ORFS "
            "hasn't picked up yet."
        ),
    )
    parser.add_argument(
        "--ignore",
        action="store_true",
        help=(
            "Downgrade 'expected to update X but found no match' failures "
            "to warnings.  Useful when MODULE.bazel has hand-edits the "
            "bumper doesn't recognize (e.g. a variable-bound version "
            "literal) and you still want the recognizable parts updated."
        ),
    )
    parser.add_argument(
        "--allow-stale-pin",
        action="store_true",
        help=(
            f"Bump even when the bazel-orfs pin is older than "
            f"{BUMP_SUPPORT_WINDOW_DAYS} days.  Unsupported and "
            "best-effort: the migration paths for that shape are gone."
        ),
    )
    parser.add_argument(
        "--check-yosys-abc",
        action="store_true",
        help="Only validate yosys/abc lockstep; don't modify MODULE.bazel.",
    )
    args = parser.parse_args()

    if args.check_yosys_abc:
        with open(args.module_file) as f:
            ok, msg = check_yosys_abc_pair(f.read())
        if not ok:
            sys.stderr.write(msg + "\n")
            sys.exit(1)
        if msg:
            sys.stderr.write(msg + "\n")
        return

    # Rolling-window gate: refuse a MODULE.bazel whose shape predates what
    # this bumper still knows how to rewrite.  The target commit is resolved
    # here, before any tarball is touched, so the failure is immediate — and
    # handed to bump() so both measure the same commit.
    target_commit = fetch_latest_commit("The-OpenROAD-Project/bazel-orfs", "main")
    if not args.allow_stale_pin:
        with open(args.module_file) as f:
            module_content = f.read()
        try:
            span = check_pin_window(module_content, target_commit)
        except StalePinError as e:
            # A traceback would bury the policy text this is here to deliver.
            sys.stderr.write(f"\nERROR: {e}\n")
            sys.exit(1)
        if span is not None:
            print(
                f"bazel-orfs pin is {span} commit-days behind the target "
                f"(window: {BUMP_SUPPORT_WINDOW_DAYS} days)"
            )

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    bump(
        args.module_file,
        workspace_dir=workspace,
        head_tools=set(args.head),
        ignore_errors=args.ignore,
        bazel_orfs_commit=target_commit,
    )
    run_mod_tidy(workspace)


if __name__ == "__main__":
    main()
