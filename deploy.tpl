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
  local renames
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
      -r|--renames)
        renames="$2"
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

  if [[ "$dst" != /* ]]; then
    echo "$progname: '$dst' is not an absolute path"
    echo "Try '$progname -h' for more information."
    exit 1
  fi

  local canonical
  canonical="$(realpath --canonicalize-missing "$dst")"

  mkdir --parents "$dst"
  chmod --recursive u+w "$dst"
  cp --recursive --target-directory "$dst" -- $0.runfiles/*
  if [ ! -d "$dst/_main/external" ]; then
    # Needed as of Bazel >= 8
    ln -sf "$dst" "$dst/_main/external"
  fi
  dst_main="$dst/_main"

  for file in $genfiles; do
    if [ -L "$dst_main/$file" ]; then
      unlink "$dst_main/$file"
    fi
    cp --force --dereference --no-preserve=all --parents --target-directory "$dst_main" "$file"
  done

  rm -f "$dst/make"
  cat > "$dst/make" <<EOF
#!/usr/bin/env bash
set -exuo pipefail
cd "\$(dirname "\$0")/_main"
exec ./$make "\$@"
EOF
  chmod +x "$dst/make"

  cp --force --no-preserve=all "$config" "$dst_main/config.mk"

  for rename in $renames; do
    IFS=':' read -r from to <<EOF
$rename
EOF
    mkdir --parents "$dst_main"/"$(dirname "$to")"
    cp --force --dereference --no-preserve=all "$from" "$dst_main"/"$to"
  done

  if [ "$#" -gt 0 ]; then
    "$dst/make" "$@"
  fi
}

main --genfiles "${GENFILES}" --renames "${RENAMES}" --make "${MAKE}" --config "${CONFIG}" "$@"
