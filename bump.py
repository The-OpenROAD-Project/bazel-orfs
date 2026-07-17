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
}


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


BAZEL_ORFS_SUBMODULES = {
    "bazel-orfs-verilog": "verilog",
}

# Substrings that imply a consumer actually uses a given submodule.  Used
# to gate submodule injection so downstream projects don't pick up
# dependencies they never reference.  Match against BUILD/*.bzl contents.
SUBMODULE_USAGE_PATTERNS = {
    "bazel-orfs-verilog": [
        "@bazel-orfs-verilog//",
    ],
}


def find_bazel_orfs_submodules(content):
    """Return the subset of BAZEL_ORFS_SUBMODULES that have git_override blocks."""
    return [
        name
        for name in BAZEL_ORFS_SUBMODULES
        if re.search(
            r'git_override\(.*?module_name\s*=\s*"' + re.escape(name) + r'"',
            content,
            re.DOTALL,
        )
    ]


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


def _openroad_submodule_patch_cmd(path, github_repo, sha, sha256_hex):
    """Render one patch_cmds curl-extract line for an OpenROAD submodule.

    Format: download to a SHA-suffixed staging file *inside the repo's own
    workdir* (not /tmp — many hosts mount /tmp as tmpfs and the OpenROAD
    submodule tarballs are large enough to matter), verify with sha256sum,
    untar with --strip-components=1 into the empty submodule directory the
    parent archive left behind, clean up.  --retry absorbs transient
    network blips (mirrors the qt-bazel xcb-util-cursor pattern in
    //MODULE.bazel).
    """
    archive_url = f"https://github.com/{github_repo}/archive/{sha}.tar.gz"
    stagefile = f".openroad-submodule-{path.replace('/', '-')}-{sha}.tar.gz"
    return (
        f"curl -sSfL --retry 5 --retry-all-errors --retry-delay 5 "
        f"-o {stagefile} {archive_url} && "
        f"echo '{sha256_hex}  {stagefile}' | sha256sum -c - && "
        f"tar xzf {stagefile} --strip-components=1 -C {path} && "
        f"rm {stagefile}"
    )


def _format_openroad_archive_override(
    openroad_commit, parent_integrity, submodule_info, patches
):
    """Render the openroad archive_override block as Starlark source text.

    ``submodule_info``: list of ``(path, github_repo, sha, sha256_hex)``.
    ``patches``: list of patch label strings (empty -> no patches/patch_strip).

    Attribute order matches buildifier convention: ``module_name`` first,
    rest alphabetical.  fix_lint will re-format anyway, but landing close
    to the final shape keeps diffs small.
    """
    parent_url = f"https://github.com/{OPENROAD_REPO}/archive/{openroad_commit}.tar.gz"
    parent_strip = f"OpenROAD-{openroad_commit}"

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
        cmd = _openroad_submodule_patch_cmd(path, github_repo, sha, sha256_hex)
        lines.append(f"        {cmd!r},")
    # OpenROAD aliases @slang -> @sv-lang//:libsvlang via
    # new_local_repository(name="slang", path="bazel"), and Bazel resolves
    # `path` against the *consumer* workspace root.  Consumers don't have
    # OpenROAD's bazel/ directory there, so the alias fetch fails the moment
    # anything references @slang.  Rewrite the lone reference in slang-elab
    # to use @sv-lang directly so the alias is never triggered.
    lines.append(
        r"""        "sed -i 's|\"@slang\"|\"@sv-lang//:libsvlang\"|' third-party/slang-elab/src/BUILD","""
    )
    lines.append("    ],")
    if patches:
        lines.append("    patch_strip = 1,")
        lines.append("    patches = [")
        for p in patches:
            lines.append(f'        "{p}",')
        lines.append("    ],")
    lines.append(f'    strip_prefix = "{parent_strip}",')
    lines.append(f'    urls = ["{parent_url}"],')
    lines.append(")")
    return "\n".join(lines)


def _extract_patches(block):
    """Return the list of patch labels found inside a Starlark block.

    Matches ``"//<path>:foo.patch"`` and ``"//:foo.patch"`` style labels —
    the only shapes used by bazel-orfs's openroad overrides today.
    """
    return re.findall(r'"(//[^"]*\.patch)"', block)


def update_openroad_archive_override(
    content,
    openroad_commit,
    fetch_integrity_fn=compute_integrity,
    fetch_sha256_hex_fn=compute_sha256_hex,
    fetch_submodule_sha_fn=fetch_submodule_sha,
):
    """Convert ``git_override(openroad, init_submodules=True)`` to
    ``archive_override`` with submodule ``patch_cmds`` — or re-update an
    existing ``archive_override(openroad)`` block in place.

    git_override + init_submodules has a long-standing reliability bug
    (interrupted fetches leave empty submodule directories that Bazel then
    reuses); archive_override is atomic.  GitHub's auto-archive of the
    parent doesn't include submodules, so this regenerates patch_cmds that
    curl each submodule's own /archive/<sha>.tar.gz and extract it in
    place.

    Returns ``content`` unchanged if neither shape is found.  Idempotent:
    invoking twice with the same commit produces identical output.
    """
    git_span = find_git_override_block(content, "openroad")
    arc_span = find_archive_override_block(content, "openroad")
    span = arc_span or git_span
    if span is None:
        return content
    start, end = span
    old_block = content[start:end]

    patches = _extract_patches(old_block)

    parent_url = f"https://github.com/{OPENROAD_REPO}/archive/{openroad_commit}.tar.gz"
    parent_integrity = fetch_integrity_fn(parent_url)
    submodule_info = []
    for path, github_repo in OPENROAD_SUBMODULES:
        sub_sha = fetch_submodule_sha_fn(OPENROAD_REPO, openroad_commit, path)
        sub_url = f"https://github.com/{github_repo}/archive/{sub_sha}.tar.gz"
        sub_sha256 = fetch_sha256_hex_fn(sub_url)
        submodule_info.append((path, github_repo, sub_sha, sub_sha256))

    new_block = _format_openroad_archive_override(
        openroad_commit, parent_integrity, submodule_info, patches
    )
    return content[:start] + new_block + content[end:]


def submodule_is_used(name, workspace_dir):
    """Return True if the workspace references the given bazel-orfs submodule.

    Scans BUILD/BUILD.bazel/*.bzl files for substrings listed in
    SUBMODULE_USAGE_PATTERNS.  Skips hidden and bazel output dirs.
    """
    patterns = SUBMODULE_USAGE_PATTERNS.get(name, [])
    if not patterns:
        return True
    for root, _dirs, files in os.walk(workspace_dir):
        rel = os.path.relpath(root, workspace_dir)
        if rel != "." and any(
            part.startswith(".") or part.startswith("bazel-")
            for part in rel.split(os.sep)
        ):
            continue
        for fname in files:
            if not (
                fname == "BUILD" or fname == "BUILD.bazel" or fname.endswith(".bzl")
            ):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath) as f:
                    text = f.read()
            except OSError:
                continue
            if any(p in text for p in patterns):
                return True
    return False


def inject_submodule_overrides(content, commit, workspace_dir=None):
    """Inject bazel_dep + git_override blocks for missing bazel-orfs submodules.

    Inserts after the bazel-orfs git_override block.  Only injects a
    submodule the consumer actually references; requires workspace_dir
    to inspect BUILD/*.bzl files.  When workspace_dir is not provided,
    no injection is performed.
    """
    if workspace_dir is None:
        return content
    missing = [
        name
        for name in BAZEL_ORFS_SUBMODULES
        if not has_bazel_dep(content, name) and submodule_is_used(name, workspace_dir)
    ]
    if not missing:
        return content

    span = find_git_override_block(content, "bazel-orfs")
    if not span:
        return content

    blocks = []
    for name in missing:
        strip_prefix = BAZEL_ORFS_SUBMODULES[name]
        blocks.append(
            f'\nbazel_dep(name = "{name}")\n'
            f"git_override(\n"
            f'    module_name = "{name}",\n'
            f'    commit = "{commit}",\n'
            f'    remote = "https://github.com/The-OpenROAD-Project/bazel-orfs",\n'
            f'    strip_prefix = "{strip_prefix}",\n'
            f")"
        )

    insert_pos = span[1]
    return content[:insert_pos] + "\n" + "\n".join(blocks) + content[insert_pos:]


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

    # Find insertion point: after the last bazel-orfs submodule git_override
    insert_pos = 0
    for name in list(BAZEL_ORFS_SUBMODULES) + ["bazel-orfs"]:
        span = find_git_override_block(content, name)
        if span and span[1] > insert_pos:
            insert_pos = span[1]
    if insert_pos == 0:
        return content

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


def fetch_compare_status(repo, base, head):
    """Return the GitHub /compare status: 'ahead' | 'behind' | 'identical' | 'diverged'."""
    url = f"https://api.github.com/repos/{repo}/compare/{base}...{head}"
    return fetch_json(url).get("status")


def bump(
    module_file,
    fetch_commit_fn=fetch_latest_commit,
    fetch_integrity_fn=compute_integrity,
    fetch_orfs_tool_sha_fn=fetch_orfs_tool_sha,
    fetch_compare_status_fn=fetch_compare_status,
    fetch_yosys_makefile_version_fn=fetch_yosys_makefile_version,
    fetch_bcr_versions_fn=fetch_bcr_versions,
    fetch_sha256_hex_fn=compute_sha256_hex,
    fetch_submodule_sha_fn=fetch_submodule_sha,
    workspace_dir=None,
    head_tools=None,
    ignore_errors=False,
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
        bazel_orfs_commit = fetch_commit_fn("The-OpenROAD-Project/bazel-orfs", "main")
        _expect(
            find_git_override_block(content, "bazel-orfs"),
            'git_override(module_name = "bazel-orfs")',
            ignore_errors,
        )
        content = update_git_override_commit(content, "bazel-orfs", bazel_orfs_commit)
        updated_modules.append(f"bazel-orfs -> {bazel_orfs_commit[:12]}")
        # Inject git_override blocks for any missing submodules that the
        # consumer actually uses.
        content = inject_submodule_overrides(content, bazel_orfs_commit, workspace_dir)
        # Submodules live in the same repo, so they share the same commit
        for submodule in find_bazel_orfs_submodules(content):
            # Existence is guaranteed by find_bazel_orfs_submodules.
            content = update_git_override_commit(content, submodule, bazel_orfs_commit)
            updated_modules.append(f"{submodule} -> {bazel_orfs_commit[:12]}")

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
        if find_archive_override_block(content, "orfs"):
            content = update_orfs_archive_override(
                content,
                orfs_commit,
                fetch_integrity_fn=fetch_integrity_fn,
                fetch_sha256_hex_fn=fetch_sha256_hex_fn,
                ignore_errors=ignore_errors,
            )
        else:
            _expect(
                find_git_override_block(content, "orfs"),
                'git_override(module_name = "orfs")',
                ignore_errors,
            )
            content = update_git_override_commit(content, "orfs", orfs_commit)
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
                # openroad is pinned via archive_override + submodule patch_cmds
                # rather than git_override (the latter's init_submodules path
                # has a non-atomic-fetch bug — see OPENROAD_REPO comment).
                # Convert legacy git_override blocks on first sight; otherwise
                # re-regenerate the existing archive_override in place.
                _expect(
                    find_git_override_block(content, "openroad")
                    or find_archive_override_block(content, "openroad"),
                    'git_override or archive_override(module_name = "openroad")',
                    ignore_errors,
                )
                content = update_openroad_archive_override(
                    content,
                    sha,
                    fetch_integrity_fn=fetch_integrity_fn,
                    fetch_sha256_hex_fn=fetch_sha256_hex_fn,
                    fetch_submodule_sha_fn=fetch_submodule_sha_fn,
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

    # --- Validate yosys/abc lockstep (downstream MODULE.bazel) ---
    # In the bump path this is informational: BCR availability and yosys
    # release cadence don't always line up (e.g. yosys 0.63 ships without
    # a matching abc 0.63-yosyshq on BCR), and blocking the bumper on that
    # would be more disruptive than the lurking quality risk. CI gets the
    # hard check via the `--check-yosys-abc` entrypoint.
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

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    bump(
        args.module_file,
        workspace_dir=workspace,
        head_tools=set(args.head),
        ignore_errors=args.ignore,
    )
    run_mod_tidy(workspace)


if __name__ == "__main__":
    main()
