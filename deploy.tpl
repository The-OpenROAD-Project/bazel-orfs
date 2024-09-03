#!/usr/bin/env bash

set -e

usage() {
  echo "Usage: $1 [ABSOLUTE_PATH]"
  exit 1
}

main() {
  local progname
  local dst
  local config
  local genfiles
  local make
  progname=$(basename "$0")

  while [ $# -gt 0 ]; do
    case $1 in
      -h|--help)
        usage "$progname"
      ;;
      -c|--config)
        config="$2"
        shift
        shift
      ;;
      -g|--genfiles)
        genfiles="$2"
        shift
        shift
      ;;
      -m|--make)
        make="$2"
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

  mkdir --parents "$dst"
  cp --recursive --parents --target-directory "$dst" -- *

  for file in $genfiles; do
    if [ -L "$dst/$file" ]; then
      unlink "$dst/$file"
    fi
    cp --force --dereference --no-preserve=all --parents --target-directory "$dst" "$file"
  done

  cp --force "$make" "$dst/make"
  cp --force --no-preserve=all "$config" "$dst/config.mk"

  if [[ "$make" == *synth* || "$make" == *canonicalize* ]]; then
    "$dst/make" yosys-dependencies
  fi

  exit $?
}

main --genfiles "${GENFILES}" --make "${MAKE}" --config "${CONFIG}" "$@"
