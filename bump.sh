#!/bin/bash
set -e -u -o pipefail

cd $BUILD_WORKSPACE_DIRECTORY

MODULE_FILE="MODULE.bazel"
REPO="openroad/orfs"
LATEST_TAG=$(curl -s "https://hub.docker.com/v2/repositories/$REPO/tags/?page_size=100" | \
    jq -r '.results | sort_by(.last_updated) | reverse | .[] | select(.name != "latest") | .name' | head -n 1)

if [[ -z "$LATEST_TAG" || "$LATEST_TAG" == "null" ]]; then
    echo "Failed to fetch latest tag."
    exit 1
fi

echo "Latest tag: $LATEST_TAG"

# Pull the latest image
docker pull "$REPO:$LATEST_TAG"

# Get the SHA-256 digest
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

COMMIT=$(curl -s "https://api.github.com/repos/The-OpenROAD-Project/bazel-orfs/commits/main" | jq -r '.sha')
if [[ -z "$COMMIT" || "$COMMIT" == "null" ]]; then
    echo "Failed to fetch latest commit."
    exit 1
fi
echo "Latest commit: $COMMIT"
sed -i "/git_override(/{:a;N;/)/!ba};/module_name = \"bazel-orfs\"/s/commit = \"[^\"]*\"/commit = \"$COMMIT\"/" MODULE.bazel

bazelisk mod tidy

git diff --color=always MODULE.bazel | cat
