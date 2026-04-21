#!/usr/bin/env python3
"""Update bazel-orfs and OpenROAD versions in MODULE.bazel.

Usage:
    python bump.py [--module-file MODULE.bazel]

Run via Bazel:
    bazelisk run //:bump
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request


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


def find_git_override_block(content, module_name):
    """Find the full git_override() block for a module, handling nested strings.

    Returns (start, end) tuple or None if not found.
    """
    pattern = r"git_override\s*\("
    for m in re.finditer(pattern, content):
        end = find_starlark_call_end(content, m.start())
        block = content[m.start() : end]
        if f'module_name = "{module_name}"' in block:
            return (m.start(), end)
    return None


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


def update_yosys_build_bzl(filepath, yosys_commit):
    """Update yosys_commit in yosys_build.bzl (inside extension.bzl yosys_build() call)."""
    with open(filepath) as f:
        content = f.read()

    content = re.sub(
        r'(yosys_commit\s*=\s*")[^"]*(")',
        rf"\g<1>{yosys_commit}\2",
        content,
    )

    with open(filepath, "w") as f:
        f.write(content)


def bump(
    module_file,
    fetch_commit_fn=fetch_latest_commit,
    fetch_release_fn=fetch_latest_github_release,
    fetch_tag_commit_fn=fetch_tag_commit,
    workspace_dir=None,
):
    """Main bump orchestrator.

    Implements the project-type matrix:
        Project      bazel-orfs  OpenROAD  ORFS     yosys
                      commit      commit   commit   release
        bazel-orfs   skip(self)  yes       yes      yes
        OpenROAD     yes         skip      skip     skip
        downstream   yes         if present skip    skip
    """
    with open(module_file) as f:
        content = f.read()

    project = detect_project(content)
    updated_modules = []

    # --- Locate bazel-orfs source (for reading overrides and copying patches) ---
    bazel_orfs_dir = os.path.dirname(os.path.abspath(__file__))

    # --- Update bazel-orfs commit (skip for bazel-orfs itself) ---
    if project != "bazel-orfs":
        bazel_orfs_commit = fetch_commit_fn("The-OpenROAD-Project/bazel-orfs", "main")
        content = update_git_override_commit(content, "bazel-orfs", bazel_orfs_commit)
        updated_modules.append(f"bazel-orfs -> {bazel_orfs_commit[:12]}")
        # Inject git_override blocks for any missing submodules that the
        # consumer actually uses.
        content = inject_submodule_overrides(content, bazel_orfs_commit, workspace_dir)
        # Submodules live in the same repo, so they share the same commit
        for submodule in find_bazel_orfs_submodules(content):
            content = update_git_override_commit(content, submodule, bazel_orfs_commit)
            updated_modules.append(f"{submodule} -> {bazel_orfs_commit[:12]}")

        # Inject non-BCR deps (orfs, openroad, qt-bazel) with commits
        # pinned to the same versions bazel-orfs uses
        content = inject_non_bcr_deps(content, bazel_orfs_dir)
        if workspace_dir:
            copy_patches(bazel_orfs_dir, workspace_dir)

    # --- Update OpenROAD commit (skip for OpenROAD itself) ---
    openroad_commit = fetch_commit_fn("The-OpenROAD-Project/OpenROAD", "master")

    if project != "openroad":
        content = update_git_override_commit(content, "openroad", openroad_commit)
        updated_modules.append(f"openroad -> {openroad_commit[:12]}")

    # --- Update ORFS commit ---
    # For bazel-orfs itself: bump to latest ORFS.
    # For downstream: ORFS commit is pinned by bazel-orfs (patches must match),
    # so only update if the override was already present (user manages their own).
    orfs_commit = fetch_commit_fn(
        "The-OpenROAD-Project/OpenROAD-flow-scripts", "master"
    )
    if project == "bazel-orfs":
        content = update_git_override_commit(content, "orfs", orfs_commit)
        updated_modules.append(f"orfs -> {orfs_commit[:12]}")

    # --- Update qt-bazel commit ---
    if has_bazel_dep(content, "qt-bazel"):
        qt_commit = fetch_commit_fn("The-OpenROAD-Project/qt_bazel_prebuilts", "main")
        content = update_git_override_commit(content, "qt-bazel", qt_commit)
        updated_modules.append(f"qt-bazel -> {qt_commit[:12]}")

    # --- Update yosys release (bazel-orfs only) ---
    if project == "bazel-orfs":
        yosys_tag = fetch_release_fn("YosysHQ/yosys")
        yosys_commit = fetch_tag_commit_fn("YosysHQ/yosys", yosys_tag)
        if workspace_dir:
            ext_file = os.path.join(workspace_dir, "extension.bzl")
            if os.path.exists(ext_file):
                update_yosys_build_bzl(ext_file, yosys_commit)
                updated_modules.append(f"yosys -> {yosys_tag} ({yosys_commit[:12]})")

    with open(module_file, "w") as f:
        f.write(content)

    # --- Summary ---
    print(f"Updated {module_file} ({project} project):")
    for entry in updated_modules:
        print(f"  {entry}")

    return content


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
    args = parser.parse_args()

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    bump(args.module_file, workspace_dir=workspace)


if __name__ == "__main__":
    main()
