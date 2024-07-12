#!/usr/bin/env bash

set -e

usage() {
  echo "Usage: $1 [ABSOLUTE_PATH]"
  exit 1
}

main() {
  local progname
  local dst
  local genfiles
  progname=$(basename "$0")

  while [ $# -gt 0 ]; do
    case $1 in
      -h|--help)
        usage "$progname"
      ;;
      -g|--genfiles)
        genfiles="$2"
        shift
        shift
      ;;
      *)
        dst="$1"
        shift
        break
      ;;
    esac
  done

  if [ -z "$dst" ]; then
    echo "$progname: must have [ABSOLUTE_PATH]"
    echo "Try '$progname -h' for more information."
    exit 1
  fi

  local canonical
  canonical="$(realpath --canonicalize-missing "$dst")"
  if [ "$dst" != "$canonical" ] && [ "$dst" != "$canonical/" ]; then
    echo "$progname: '$dst' is not an absolute path"
    echo "Try '$progname -h' for more information."
    exit 1
  fi

  if [ ! -e "$dst" ]; then
    echo "$progname: '$dst' does not exist"
    echo "Try '$progname -h' for more information."
    exit 1
  fi

  if [ ! -d "$dst" ]; then
    echo "$progname: '$dst' is not a directory"
    echo "Try '$progname -h' for more information."
    exit 1
  fi

  cp --recursive --parents --target-directory "$dst" -- *

  for file in $genfiles; do
    if [ -L "$dst/$file" ]; then
      unlink "$dst/$file"
    fi
    cp --force --dereference --no-preserve=all --parents --target-directory "$dst" "$file"
  done

  exit $?
}

main --genfiles "${GENFILES}" "$@"