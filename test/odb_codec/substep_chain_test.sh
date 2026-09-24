#!/bin/sh
# gcd's floorplan and place substep .odb files, stored as deltas: each is
# stored against the next file of its stage, decodes, and is a database
# openroad reads through ODB_CODEC and writes back unchanged.
#
#   substep_chain_test.sh OPENROAD ODB_CODEC FILE.odb...
set -eu
openroad=$(realpath "$1")
codec=$(realpath "$2")
shift 2
work=${TEST_TMPDIR:-$(mktemp -d)}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

checked=0
for odb do
  name=$(basename "$odb" .odb)
  case "$name" in
  2_floorplan | 3_place)
    [ -z "$("$codec" base "$odb")" ] || fail "$name, a stage output, is a delta"
    ;;
  *)
    base=$("$codec" base "$odb")
    [ -n "$base" ] || fail "$name is not stored against the next substep"
    [ -e "$(dirname "$odb")/$base" ] || fail "$name: base $base is missing"
    ;;
  esac
  "$codec" decode "$odb" >"$work/$name.decoded" || fail "$name does not decode"
  printf 'read_db %s\nunset ::env(ODB_CODEC)\nwrite_db %s\n' \
    "$odb" "$work/$name.rewritten" >"$work/$name.tcl"
  ODB_CODEC=$codec "$openroad" -no_init -no_splash -exit "$work/$name.tcl" \
    >"$work/$name.log" 2>&1 || fail "openroad cannot read $name: $(tail -3 "$work/$name.log")"
  cmp -s "$work/$name.decoded" "$work/$name.rewritten" ||
    fail "$name: openroad's database differs from the decoded file"
  checked=$((checked + 1))
done
[ "$checked" -ge 11 ] || fail "only $checked files checked"
echo "substep chain: $checked files ok"
