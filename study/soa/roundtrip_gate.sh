#!/usr/bin/env bash
# Round-trip gate for the field-major .odb format, plus the artifact size it
# actually produces.
#
# Three questions, in the order a reviewer would ask them:
#   1. Is anything observable different?  Compare the DEF written from the
#      original database against the DEF written after a field-major round
#      trip. Equal DEFs mean no object moved, no id changed, no iteration
#      order shifted -- the things a permutation of the byte stream must not
#      touch.
#   2. Is the new format stable?  Write it, read it, write it again, and
#      require the two files to be byte-identical.
#   3. What does it buy?  Compressed size of the original against the
#      field-major artifact, with the real codecs.
#
# usage: roundtrip_gate.sh <openroad> <design.odb> <workdir> [csv]
set -euo pipefail

binary="$(readlink -f "${1:?openroad binary}")"
design="$(readlink -f "${2:?design .odb}")"
work="${3:?work directory}"
csv="${4:-/dev/stdout}"
name="$(basename "$design" .odb)"

mkdir -p "$work"
cd "$work"

cat > pass0.tcl <<TCL
read_db $design
write_def ${name}.orig.def
TCL
cat > pass1.tcl <<TCL
read_db $design
write_db ${name}.fm.odb
TCL
cat > pass2.tcl <<TCL
read_db ${name}.fm.odb
write_def ${name}.fm.def
write_db ${name}.fm2.odb
TCL

"$binary" -no_init -exit pass0.tcl > ${name}.pass0.log 2>&1
"$binary" -no_init -exit pass1.tcl > ${name}.pass1.log 2>&1
"$binary" -no_init -exit pass2.tcl > ${name}.pass2.log 2>&1

def_equal=no
cmp -s ${name}.orig.def ${name}.fm.def && def_equal=yes
stable=no
cmp -s ${name}.fm.odb ${name}.fm2.odb && stable=yes

size() { stat -c %s "$1"; }
zsize() { zstd -3 -c -T0 --no-progress "$1" | wc -c; }
gsize() { gzip -6 -c "$1" | wc -c; }

if [ ! -s "$csv" ]; then
  echo "design,def_equal,stable,raw_before,raw_after,zstd_before,zstd_after,gzip_before,gzip_after" > "$csv"
fi
echo "${name},${def_equal},${stable},$(size "$design"),$(size ${name}.fm.odb),$(zsize "$design"),$(zsize ${name}.fm.odb),$(gsize "$design"),$(gsize ${name}.fm.odb)" >> "$csv"
