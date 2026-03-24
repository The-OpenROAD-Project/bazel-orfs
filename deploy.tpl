#!/usr/bin/env bash

set -e

usage() {
  echo "Usage: $1 [--install <dir>] [<make args...>]"
  echo "  Files are placed in \$BUILD_WORKSPACE_DIRECTORY/tmp/<package>/<name>"
  echo "  --install <dir>  Override the installation directory"
  exit 1
}

main() {
  local progname
  local config
  local genfiles
  local renames
  local make
  local name="${NAME}"
  local package="${PACKAGE}"
  local install_dir=""
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
      -n|--name)
        name="$2"
        shift
        shift
      ;;
      --install)
        install_dir="$2"
        shift
        shift
      ;;
      *)
        break
      ;;
    esac
  done

  if [ -z "$BUILD_WORKSPACE_DIRECTORY" ]; then
    echo "$progname: must be run via 'bazel run'"
    echo "Try '$progname -h' for more information."
    exit 1
  fi

  local dst
  if [ -n "$install_dir" ]; then
    dst="$install_dir"
  else
    dst="${BUILD_WORKSPACE_DIRECTORY}/tmp${package:+/$package}/$name"
  fi

  if [ -z "$install_dir" ]; then
    local missing=()
    if ! grep -qxF "tmp/" "$BUILD_WORKSPACE_DIRECTORY/.gitignore" 2>/dev/null; then
      missing+=(".gitignore")
    fi
    if ! grep -qxF "tmp" "$BUILD_WORKSPACE_DIRECTORY/.bazelignore" 2>/dev/null; then
      missing+=(".bazelignore")
    fi
    if [ ${#missing[@]} -gt 0 ]; then
      echo "$progname: 'tmp' entry missing from: ${missing[*]}"
      echo "Add 'tmp/' to .gitignore and 'tmp' to .bazelignore"
      exit 1
    fi
  fi

  mkdir --parents "$dst"
  chmod --recursive u+w "$dst"
  cp --recursive --target-directory "$dst" -- $0.runfiles/*
  if [ ! -d "$dst/_main/external" ]; then
    # Needed as of Bazel >= 8: _main/external/<repo> must resolve.
    # Create a real directory with per-repo symlinks instead of
    # ln -sf "$dst" which creates a self-referential loop that
    # causes tar -ch (follow symlinks) to recurse infinitely.
    mkdir -p "$dst/_main/external"
    for repo_dir in "$dst"/*/; do
      repo_name=$(basename "$repo_dir")
      [ "$repo_name" = "_main" ] && continue
      [ "$repo_name" = "_repo_mapping" ] && continue
      ln -sf "$repo_dir" "$dst/_main/external/$repo_name"
    done
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

main --genfiles "${GENFILES}" --name "${NAME}" --renames "${RENAMES}" --make "${MAKE}" --config "${CONFIG}" "$@"
