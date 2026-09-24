#!/bin/sh
# A stand-in ODB_CODEC for codec_hook_test.sh: encode checks the layout
# describes the file and prefixes a marker line, decode strips it and
# hands any other file over unchanged.
set -e
marker=stub-codec
case "$1" in
encode)
  size=$(wc -c <"$2")
  head -n 1 "$3" | grep -qx 'odb-layout 1'
  tail -n 1 "$3" | grep -qx "size $((size))"
  { echo "$marker"; cat "$2"; } >"$2.stub"
  mv "$2.stub" "$2"
  ;;
decode)
  if [ "$(head -n 1 "$2")" = "$marker" ]; then
    tail -n +2 "$2"
  else
    cat "$2"
  fi
  ;;
*) exit 2 ;;
esac
