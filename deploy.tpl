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
  # A directory that an earlier deploy turned from a link into a copy (see
  # below) is in the way of the link cp is about to lay down again.
  if [ -d "$dst/_main" ]; then
    (cd "$0.runfiles/_main" && find . -path ./external -prune -o -type l -print) |
      while IFS= read -r rel; do
        if [ -d "$dst/_main/$rel" ] && [ ! -L "$dst/_main/$rel" ]; then
          rm -rf "${dst:?}/_main/$rel"
        fi
      done
  fi
  cp --recursive --target-directory "$dst" -- $0.runfiles/*
  # Needed as of Bazel >= 8: _main/external/<repo> must resolve.
  # Create a real directory with per-repo symlinks instead of
  # ln -sf "$dst" which creates a self-referential loop that
  # causes tar -ch (follow symlinks) to recurse infinitely.
  # Recreate on every deploy so newly added repos get symlinked.
  rm -rf "$dst/_main/external"
  mkdir -p "$dst/_main/external"
  for repo_dir in "$dst"/*/; do
    repo_name=$(basename "$repo_dir")
    [ "$repo_name" = "_main" ] && continue
    [ "$repo_name" = "_repo_mapping" ] && continue
    ln -sf "$repo_dir" "$dst/_main/external/$repo_name"
  done
  # Bazel modules use canonical names with '+' suffix (e.g. tcl_lang+).
  # C++ runfiles libraries look up apparent names without '+' (e.g. tcl_lang).
  # Create symlinks so both names resolve.
  for repo_dir in "$dst"/*+/; do
    [ -d "$repo_dir" ] || continue
    apparent="${repo_dir%+/}"
    [ -e "$apparent" ] && continue
    ln -sf "$(basename "$repo_dir")" "$apparent"
  done
  dst_main="$dst/_main"

  for file in $genfiles; do
    if [ -L "$dst_main/$file" ]; then
      unlink "$dst_main/$file"
    fi
    # Skip if source and dest resolve to the same file (e.g. //:deps symlink tree).
    if [ "$(readlink -f "$file")" = "$(readlink -f "$dst_main/$file")" ] 2>/dev/null; then
      continue
    fi
    cp --force --dereference --no-preserve=all --parents --target-directory "$dst_main" "$file"
  done

  # The runfiles copied above are symlinks, and the previous stage's
  # results among them (1_synth.odb, the netlist, a memories directory,
  # the blocks' .lef/.lib) point into bazel's output tree. A chmod and an
  # edit through one of them changes a bazel action output in place;
  # bazel notices the changed metadata on the next build and re-runs the
  # action, and until then the build tree carries the hand-edited file.
  # Every link to this configuration's outputs becomes a copy (a reflink
  # where the filesystem has them). The make script is one of those
  # outputs, so its path names the configuration's bin directory. Tools
  # built for the exec configuration, external repositories and nested
  # .runfiles trees stay links: the tree reads them and never edits them.
  local out_bin
  out_bin=$(readlink -f "$make" | sed -n 's|^\(.*/bazel-out/[^/]*/bin/\).*|\1|p')
  if [ -n "$out_bin" ]; then
    find "$dst_main" -path "$dst_main/external" -prune -o -type l -print |
      while IFS= read -r link; do
        target=$(readlink -f "$link") || continue
        case "$target" in
          *.runfiles | *.runfiles/*) continue ;;
          "$out_bin"*) ;;
          *) continue ;;
        esac
        rm -f "$link"
        cp --recursive --dereference --reflink=auto --preserve=mode,timestamps "$target" "$link" || exit 1
      done
  fi

  rm -f "$dst/make"
  cat > "$dst/make" <<EOF
#!/usr/bin/env bash
set -exuo pipefail
cd "\$(dirname "\$0")/_main"
# Deployed files may be read-only (symlinks into Bazel cache).
# Make them writable so that make targets can overwrite stage outputs.
find . -not -perm -u+w -exec chmod u+w {} + 2>/dev/null || true
# Point rules_cc runfiles library at the deployed runfiles tree
export RUNFILES_DIR="\$(pwd)/.."
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
