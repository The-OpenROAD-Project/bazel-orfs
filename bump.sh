#!/bin/bash
set -x -e -u -o pipefail

MODULE_FILE="MODULE.bazel"
REPO="openroad/orfs"

# Get the latest tag from Docker Hub API
LATEST_TAG=$(curl -s "https://hub.docker.com/v2/repositories/$REPO/tags/?page_size=1" | jq -r '.results[0].name')

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

# Find the section below in MODULE.bazel and update it.
# Ignore other image and sha256 fields
# orfs.default(
#      # a local only or remote docker image. Local docker images do not
#      # have a sha256.
#     image = "docker.io/openroad/orfs:v3.0-2487-g1adb9c6e",
#     sha256 = "sha256:546fb1bfabbfec4fa03c3c25ff60dbf6478daf237cb0387b35e4a3218ad2c805",
# )

sed -i -E \
    -e "/orfs\.default\(/,/^\s*\)/ { \
        s|(image = \"docker.io/openroad/orfs:)[^\"]+(\")|\1$LATEST_TAG\2|; \
        s|(sha256 = \")[^\"]+(\")|\1sha256:$DIGEST\2| \
    }" \
    "$MODULE_FILE"

bazelisk mod tidy

git diff MODULE.bazel

