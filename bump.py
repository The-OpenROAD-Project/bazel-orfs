#!/usr/bin/env python3
"""Update ORFS image, bazel-orfs, and OpenROAD versions in MODULE.bazel.

Replaces bump.sh with a testable Python implementation.

Usage:
    python bump.py [--module-file MODULE.bazel] [--mock-modules dir/MODULE.bazel ...]

Run via Bazel:
    bazelisk run //:bump
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

import oci_extract


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


def update_orfs_image(content, tag, digest):
    """Update image tag and sha256 in orfs.default() block."""

    def replace_in_block(m):
        block = m.group(0)
        block = re.sub(
            r'(image\s*=\s*"docker\.io/openroad/orfs:)[^"]*(")',
            rf"\g<1>{tag}\2",
            block,
        )
        block = re.sub(
            r'(sha256\s*=\s*")[^"]*(")',
            rf"\g<1>{digest}\2",
            block,
        )
        return block

    return re.sub(
        r"orfs\.default\(.*?\)",
        replace_in_block,
        content,
        flags=re.DOTALL,
    )


def update_git_override_commit(content, module_name, new_commit):
    """Update commit in git_override() block for a given module_name.

    Handles both active and commented-out blocks.
    """

    def replace_in_block(m):
        block = m.group(0)
        if f'module_name = "{module_name}"' not in block:
            return block
        return re.sub(
            r'(commit\s*=\s*")[^"]*(")',
            rf"\g<1>{new_commit}\2",
            block,
        )

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
        return re.sub(
            r'(commit\s*=\s*")[^"]*(")',
            rf"\g<1>{new_commit}\2",
            block,
        )

    content = re.sub(
        r"#\s*git_override\((?:\n#.*?)*?\n#\s*\)",
        replace_commented_block,
        content,
    )

    return content


BAZEL_ORFS_SUBMODULES = ["bazel-orfs-verilog", "bazel-orfs-sby"]

# Old load path -> new load path.  Applied to BUILD* and *.bzl files
# when bumping a downstream project so that moved .bzl files don't
# break the build.
LOAD_MIGRATIONS = {
    '@bazel-orfs//:sby.bzl': '@bazel-orfs//:sby/sby.bzl',
}


def migrate_load_paths(workspace_dir):
    """Rewrite load() statements in BUILD/bzl files for known .bzl moves.

    Returns list of (filepath, old, new) tuples for each replacement made.
    """
    changes = []
    for root, _dirs, files in os.walk(workspace_dir):
        # Skip bazel output dirs and hidden dirs
        rel = os.path.relpath(root, workspace_dir)
        if rel != "." and any(
            part.startswith(".") or part.startswith("bazel-")
            for part in rel.split(os.sep)
        ):
            continue
        for fname in files:
            if not (
                fname == "BUILD"
                or fname == "BUILD.bazel"
                or fname.endswith(".bzl")
            ):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath) as f:
                content = f.read()
            new_content = content
            for old_path, new_path in LOAD_MIGRATIONS.items():
                new_content = new_content.replace(
                    f'"{old_path}"', f'"{new_path}"'
                )
            if new_content != content:
                with open(fpath, "w") as f:
                    f.write(new_content)
                for old_path, new_path in LOAD_MIGRATIONS.items():
                    if f'"{old_path}"' in content:
                        changes.append((fpath, old_path, new_path))
    return changes


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


BOILERPLATE_MARKER = "Uncomment to build OpenROAD from source"

BOILERPLATE_TEMPLATE = """\

# Uncomment to build OpenROAD from source instead of using the ORFS image.
# This is useful to test the latest OpenROAD before the ORFS image is updated.
# See: https://github.com/The-OpenROAD-Project/bazel-orfs/blob/main/docs/openroad.md
#
# bazel_dep(name = "openroad")
# git_override(
#     module_name = "openroad",
#     commit = "{openroad_commit}",
#     init_submodules = True,
#     patch_strip = 1,
#     patches = ["@bazel-orfs//:openroad-llvm-root-only.patch", \
"@bazel-orfs//:openroad-visibility.patch"],
#     remote = "https://github.com/The-OpenROAD-Project/OpenROAD.git",
# )
# bazel_dep(name = "qt-bazel")
# git_override(
#     module_name = "qt-bazel",
#     commit = "df022f4ebaa4130713692fffd2f519d49e9d0b97",
#     remote = "https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts",
# )
# bazel_dep(name = "toolchains_llvm", version = "1.5.0")"""


def inject_openroad_boilerplate(content, openroad_commit):
    """Inject commented-out OpenROAD-from-source boilerplate.

    Injected after the last use_repo(orfs, ...) line.
    Only if not already present.
    """
    if BOILERPLATE_MARKER in content:
        return content

    lines = content.split("\n")
    inject_after = None
    for i, line in enumerate(lines):
        if "use_repo(orfs" in line:
            inject_after = i

    if inject_after is None:
        return content

    boilerplate = BOILERPLATE_TEMPLATE.format(
        openroad_commit=openroad_commit,
    )

    lines.insert(inject_after + 1, boilerplate)
    return "\n".join(lines)


def fetch_json(url):
    """Fetch JSON from a URL."""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def fetch_latest_docker_tag(repo):
    """Get the latest non-'latest' tag from Docker Hub."""
    url = f"https://hub.docker.com/v2/repositories/{repo}" "/tags/?page_size=100"
    data = fetch_json(url)
    tags = sorted(
        [t for t in data["results"] if t["name"] != "latest"],
        key=lambda t: t["last_updated"],
        reverse=True,
    )
    if not tags:
        raise RuntimeError(f"No tags found for {repo}")
    return tags[0]["name"]


def fetch_latest_commit(github_repo, branch):
    """Get the latest commit SHA from a GitHub repo."""
    url = f"https://api.github.com/repos/{github_repo}" f"/commits/{branch}"
    data = fetch_json(url)
    sha = data.get("sha")
    if not sha:
        raise RuntimeError(f"Failed to fetch commit from {github_repo}/{branch}")
    return sha


def resolve_image_digest(image, tag):
    """Resolve an image tag to its sha256 digest."""
    registry, repository = oci_extract.parse_image(image)
    token = oci_extract.get_token(registry, repository)
    digest = oci_extract.resolve_digest(registry, repository, tag, token)
    return digest.replace("sha256:", "")


def bump(
    module_file,
    mock_modules=None,
    fetch_tag_fn=fetch_latest_docker_tag,
    fetch_commit_fn=fetch_latest_commit,
    resolve_digest_fn=resolve_image_digest,
    workspace_dir=None,
):
    """Main bump orchestrator.

    Implements the project-type matrix:
        Project      bazel-orfs   OpenROAD   docker   boilerplate
                      commit       commit     image
        bazel-orfs   skip(self)   yes        yes      skip(has it)
        OpenROAD     yes          skip(self) yes      skip(is OR)
        downstream   yes          if present yes      yes
    """
    with open(module_file) as f:
        content = f.read()

    project = detect_project(content)
    print(f"Detected: {project} project")

    # --- Update ORFS image (all projects) ---
    repo = "openroad/orfs"
    latest_tag = fetch_tag_fn(repo)
    print(f"Latest ORFS tag: {latest_tag}")

    digest = resolve_digest_fn(f"docker.io/{repo}", latest_tag)
    print(f"Digest: {digest}")

    content = update_orfs_image(content, latest_tag, digest)

    # --- Update bazel-orfs commit (skip for bazel-orfs itself) ---
    if project != "bazel-orfs":
        bazel_orfs_commit = fetch_commit_fn("The-OpenROAD-Project/bazel-orfs", "main")
        print(f"Latest bazel-orfs commit: {bazel_orfs_commit}")
        content = update_git_override_commit(content, "bazel-orfs", bazel_orfs_commit)
        # Submodules live in the same repo, so they share the same commit
        for submodule in find_bazel_orfs_submodules(content):
            content = update_git_override_commit(content, submodule, bazel_orfs_commit)

    # --- Update OpenROAD commit (skip for OpenROAD itself) ---
    openroad_commit = fetch_commit_fn("The-OpenROAD-Project/OpenROAD", "master")
    print(f"Latest OpenROAD commit: {openroad_commit}")

    if project != "openroad":
        content = update_git_override_commit(content, "openroad", openroad_commit)

    # --- Informational: ORFS commit ---
    orfs_commit = fetch_commit_fn(
        "The-OpenROAD-Project/OpenROAD-flow-scripts", "master"
    )
    print(f"Latest ORFS commit: {orfs_commit}")

    # --- Inject boilerplate (downstream only) ---
    if project == "downstream":
        content = inject_openroad_boilerplate(content, openroad_commit)

    with open(module_file, "w") as f:
        f.write(content)

    # --- Migrate load() paths for moved .bzl files (downstream only) ---
    if project != "bazel-orfs" and workspace_dir:
        changes = migrate_load_paths(workspace_dir)
        for fpath, old, new in changes:
            print(f"Migrated load path in {fpath}: {old} -> {new}")

    # --- Update mock modules ---
    if mock_modules:
        for mock_file in mock_modules:
            if not os.path.exists(mock_file):
                continue
            with open(mock_file) as f:
                mock_content = f.read()
            if "orfs.default" not in mock_content:
                continue
            print(f"Updating ORFS image in {mock_file}")
            mock_content = update_orfs_image(mock_content, latest_tag, digest)
            with open(mock_file, "w") as f:
                f.write(mock_content)

    return content


def main():
    parser = argparse.ArgumentParser(description="Bump ORFS and dependency versions")
    parser.add_argument(
        "--module-file",
        default=os.path.join(
            os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."),
            "MODULE.bazel",
        ),
        help="Path to MODULE.bazel",
    )
    parser.add_argument(
        "--mock-modules",
        nargs="*",
        default=None,
        help="Additional MODULE.bazel files to update",
    )
    args = parser.parse_args()

    # Auto-discover mock modules if not specified
    if args.mock_modules is None:
        workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
        mock_dir = os.path.join(workspace, "mock")
        if os.path.isdir(mock_dir):
            args.mock_modules = [
                os.path.join(mock_dir, d, "MODULE.bazel")
                for d in os.listdir(mock_dir)
                if os.path.isfile(os.path.join(mock_dir, d, "MODULE.bazel"))
            ]
        else:
            args.mock_modules = []

    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY", ".")
    bump(args.module_file, args.mock_modules, workspace_dir=workspace)

    # Run bazelisk mod tidy
    try:
        subprocess.run(
            ["bazelisk", "mod", "tidy"],
            cwd=workspace,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(
            f"WARNING: bazelisk mod tidy failed: {e}. "
            "You may need to run it manually.",
            file=sys.stderr,
        )

    # Show diff (workspace-wide, not just MODULE.bazel, to include load path migrations)
    subprocess.run(
        ["git", "diff", "--color=always"],
        cwd=workspace,
    )


if __name__ == "__main__":
    main()
