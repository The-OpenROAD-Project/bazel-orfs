#!/usr/bin/env bash
# bazelisk run //docs/demos/ramps:save -- <dir>: the rendered video and its
# .srt copied into <dir>, which is made if missing. A relative <dir> is
# relative to where bazelisk ran.
set -euo pipefail
[ $# -ge 2 ] || {
    echo "usage: bazelisk run //docs/demos/ramps:save -- <dir>" >&2
    exit 1
}
dest="${!#}"
case "$dest" in
/*) ;;
*) dest="${BUILD_WORKING_DIRECTORY:-$PWD}/$dest" ;;
esac
mkdir -p "$dest"
for f in "${@:1:$#-1}"; do
    cp -f "$f" "$dest/"
    chmod u+w "$dest/$(basename "$f")"
    echo "saved $dest/$(basename "$f")"
done
