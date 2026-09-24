#!/bin/sh
# The carried OpenROAD patch (patches/0005) with a stand-in codec and with
# tools/odb_codec: write_db hands the file to ODB_CODEC and removes the
# layout, read_db reads through it, unset ODB_CODEC writes no layout, and
# a file that decodes to no database fails read_db instead of aborting.
#
#   codec_hook_test.sh OPENROAD STUB_CODEC ODB_CODEC DESIGN.odb
set -eu
openroad=$(realpath "$1")
stub=$(realpath "$2")
codec=$(realpath "$3")
design=$(realpath "$4")
cd "${TEST_TMPDIR:-$(mktemp -d)}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# rewrite IN OUT [READ_CODEC [WRITE_CODEC]]: read_db IN, write_db OUT,
# each with ODB_CODEC as given, or unset.
rewrite() {
  {
    if [ -n "${3:-}" ]; then echo "set ::env(ODB_CODEC) $3"; fi
    echo "read_db $1"
    echo "unset -nocomplain ::env(ODB_CODEC)"
    if [ -n "${4:-}" ]; then echo "set ::env(ODB_CODEC) $4"; fi
    echo "write_db $2"
  } >rewrite.tcl
  env -u ODB_CODEC "$openroad" -no_init -no_splash -exit rewrite.tcl
}

# design.odb is of an older schema, so compare what read_db makes of a
# file this openroad wrote: plain.odb, read and written again.
rewrite "$design" plain.odb
[ -e plain.odb.layout ] && fail "a layout was written without ODB_CODEC"
rewrite plain.odb plain2.odb

rewrite plain.odb stub.odb "" "$stub"
[ "$(head -n 1 stub.odb)" = stub-codec ] || fail "write_db did not run the codec"
[ -e stub.odb.layout ] && fail "write_db left its layout behind"
rewrite stub.odb from_stub.odb "$stub"
cmp plain2.odb from_stub.odb || fail "read_db through the stub changed the database"

rewrite plain.odb coded.odb "" "$codec"
[ "$(head -c 8 coded.odb)" = ODBCODEC ] || fail "odb_codec did not encode"
rewrite coded.odb from_codec.odb "$codec"
cmp plain2.odb from_codec.odb || fail "odb_codec round trip changed the database"

head -c 100000 /dev/zero | tr '\0' x >bogus.odb
printf 'read_db bogus.odb\n' >bogus.tcl
status=0
ODB_CODEC=$stub "$openroad" -no_init -no_splash -exit bogus.tcl >bogus.log 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "read_db accepted a bogus file"
[ "$status" -lt 128 ] || fail "read_db of a bogus file killed openroad (status $status)"
grep -q "not an OpenDB Database" bogus.log || fail "unexpected error: $(cat bogus.log)"

echo "codec hook: ok ($(wc -c <plain.odb) byte database, $(wc -c <coded.odb) encoded)"
