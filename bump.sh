#!/bin/bash
set -e -u -o pipefail

cd $BUILD_WORKSPACE_DIRECTORY

MODULE_FILE="MODULE.bazel"

# //:bump is one user-facing interface for updating versions across four
# project types. It detects the context by checking the module name and
# conditionally runs the appropriate updates:
#
# Project         module name   bazel-orfs  OpenROAD  docker  OR boilerplate
#                               commit      commit    image   injection
# --------------- -----------   ----------  --------  ------  --------------
# bazel-orfs      bazel-orfs    skip(self)  yes       yes     skip(has it)
# OpenROAD        openroad      yes         skip(self) yes    skip(is OR)
# ORFS/user       other         yes         if present yes    yes
#
# Extract the module name from the module() declaration (first name = "..." after ^module()
MODULE_NAME=$(sed -n '/^module(/,/^)/{s/.*name = "\([^"]*\)".*/\1/p}' "$MODULE_FILE" | head -1)
IS_BAZEL_ORFS=0
IS_OPENROAD=0
[[ "$MODULE_NAME" == "bazel-orfs" ]] && IS_BAZEL_ORFS=1
[[ "$MODULE_NAME" == "openroad" ]] && IS_OPENROAD=1

if [[ "$IS_BAZEL_ORFS" -gt 0 ]]; then
    echo "Detected: bazel-orfs project"
elif [[ "$IS_OPENROAD" -gt 0 ]]; then
    echo "Detected: OpenROAD project"
else
    echo "Detected: downstream project"
fi

# --- Update ORFS docker image (all projects) ---

REPO="openroad/orfs"
LATEST_TAG=$(curl -s "https://hub.docker.com/v2/repositories/$REPO/tags/?page_size=100" | \
    jq -r '.results | sort_by(.last_updated) | reverse | .[] | select(.name != "latest") | .name' | head -n 1)

if [[ -z "$LATEST_TAG" || "$LATEST_TAG" == "null" ]]; then
    echo "Failed to fetch latest tag."
    exit 1
fi

echo "Latest ORFS docker tag: $LATEST_TAG"

docker pull "$REPO:$LATEST_TAG"

DIGEST=$(docker inspect --format='{{index .RepoDigests 0}}' "$REPO:$LATEST_TAG" | cut -d'@' -f2)
DIGEST=${DIGEST#sha256:}

if [[ -z "$DIGEST" ]]; then
    echo "Failed to fetch SHA-256 digest."
    exit 1
fi

sed -i -E \
    -e "/orfs\.default\(/,/^\s*\)/ { \
        s|(image = \"docker.io/openroad/orfs:)[^\"]+(\")|\1$LATEST_TAG\2|; \
        s|(sha256 = \")[^\"]+(\")|\1$DIGEST\2| \
    }" \
    "$MODULE_FILE"

# Also update mock downstream repos that pin the ORFS image.
for mock_module in mock/*/MODULE.bazel; do
    if [ -f "$mock_module" ] && grep -q 'orfs\.default' "$mock_module"; then
        echo "Updating ORFS image in $mock_module"
        sed -i -E \
            -e "/orfs\.default\(/,/^\s*\)/ { \
                s|(image = \"docker.io/openroad/orfs:)[^\"]+(\")|\1$LATEST_TAG\2|; \
                s|(sha256 = \")[^\"]+(\")|\1$DIGEST\2| \
            }" \
            "$mock_module"
    fi
done

# --- Update bazel-orfs commit (all projects except bazel-orfs itself) ---

if [[ "$IS_BAZEL_ORFS" -eq 0 ]]; then
    BAZEL_ORFS_COMMIT=$(curl -s "https://api.github.com/repos/The-OpenROAD-Project/bazel-orfs/commits/main" | jq -r '.sha')
    if [[ -z "$BAZEL_ORFS_COMMIT" || "$BAZEL_ORFS_COMMIT" == "null" ]]; then
        echo "Failed to fetch latest bazel-orfs commit."
        exit 1
    fi
    echo "Latest bazel-orfs commit: $BAZEL_ORFS_COMMIT"
    sed -i "/git_override(/{:a;N;/)/!ba};/module_name = \"bazel-orfs\"/s/commit = \"[^\"]*\"/commit = \"$BAZEL_ORFS_COMMIT\"/" "$MODULE_FILE"
fi

# --- Update OpenROAD commit (all projects except OpenROAD itself) ---

OPENROAD_COMMIT=$(curl -s "https://api.github.com/repos/The-OpenROAD-Project/OpenROAD/commits/master" | jq -r '.sha')
if [[ -z "$OPENROAD_COMMIT" || "$OPENROAD_COMMIT" == "null" ]]; then
    echo "Failed to fetch latest OpenROAD commit."
    exit 1
fi
echo "Latest OpenROAD commit: $OPENROAD_COMMIT"

if [[ "$IS_OPENROAD" -eq 0 ]]; then
    # Update openroad git_override commit — works on both active and commented-out code.
    # The sed pattern matches 'commit = "..."' in any git_override block containing
    # module_name = "openroad", whether or not lines are prefixed with #.
    sed -i "/git_override(/{:a;N;/)/!ba};/module_name = \"openroad\"/s/commit = \"[^\"]*\"/commit = \"$OPENROAD_COMMIT\"/" "$MODULE_FILE"
    sed -i "/#.*git_override(/{:a;N;/#.*)/!ba};/module_name = \"openroad\"/s/commit = \"[^\"]*\"/commit = \"$OPENROAD_COMMIT\"/" "$MODULE_FILE"
fi

# Informational: show latest ORFS commit for reference
ORFS_COMMIT=$(curl -s "https://api.github.com/repos/The-OpenROAD-Project/OpenROAD-flow-scripts/commits/master" | jq -r '.sha')
echo "Latest ORFS commit: ${ORFS_COMMIT:-unknown}"

# --- Inject commented-out OpenROAD-from-source boilerplate (downstream projects only) ---
# Skip for bazel-orfs (already has it) and OpenROAD (builds itself).
# Detect existing boilerplate by looking for the marker comment.

if [[ "$IS_BAZEL_ORFS" -eq 0 ]] && [[ "$IS_OPENROAD" -eq 0 ]]; then
    if ! grep -q 'Uncomment to build OpenROAD from source' "$MODULE_FILE"; then
        echo "Injecting commented-out OpenROAD-from-source boilerplate..."
        # Inject after the last use_repo(orfs, ...) line
        INJECT_AFTER=$(grep -n 'use_repo(orfs' "$MODULE_FILE" | tail -1 | cut -d: -f1)
        if [[ -n "$INJECT_AFTER" ]]; then
            sed -i "${INJECT_AFTER}a\\
\\
# Uncomment to build OpenROAD from source instead of using the docker image.\\
# This is useful to test the latest OpenROAD before the docker image is updated.\\
# See: https://github.com/The-OpenROAD-Project/bazel-orfs/blob/main/docs/openroad.md\\
#\\
# bazel_dep(name = \"openroad\")\\
# git_override(\\
#     module_name = \"openroad\",\\
#     commit = \"$OPENROAD_COMMIT\",\\
#     init_submodules = True,\\
#     patch_strip = 1,\\
#     patches = [\"@bazel-orfs//:openroad-llvm-root-only.patch\", \"@bazel-orfs//:openroad-visibility.patch\"],\\
#     remote = \"https://github.com/The-OpenROAD-Project/OpenROAD.git\",\\
# )\\
# bazel_dep(name = \"qt-bazel\")\\
# git_override(\\
#     module_name = \"qt-bazel\",\\
#     commit = \"df022f4ebaa4130713692fffd2f519d49e9d0b97\",\\
#     remote = \"https://github.com/The-OpenROAD-Project/qt_bazel_prebuilts\",\\
# )\\
# bazel_dep(name = \"toolchains_llvm\", version = \"1.5.0\")" \
            "$MODULE_FILE"
        fi
    else
        echo "OpenROAD-from-source boilerplate already present, updating commit..."
    fi
fi

# mod tidy may fail when using local_path_override for bazel-orfs
# (dev dependencies like mock-klayout aren't visible to non-root consumers).
# The MODULE.bazel edits above are already done, so this is best-effort.
bazelisk mod tidy || echo "WARNING: bazelisk mod tidy failed. You may need to run it manually after fixing MODULE.bazel."

git diff --color=always "$MODULE_FILE" | cat
