#!/bin/sh
# Builds the asap7 designs below with and without //tools/odb_codec and
# measures every .odb their stages write (measure.py). From the workspace
# root, for every design or only the ones named:
#
#   test/odb_codec/measure.sh [gcd uart ...]
#
# JOBS (default 12) bounds the flows run at once; these designs are
# small enough that memory does not bind. A large design wants 2.
set -eu
JOBS=${JOBS:-12}

DESIGNS="
gcd @orfs//flow/designs/asap7/gcd:gcd
uart @orfs//flow/designs/asap7/uart:uart
riscv32i @orfs//flow/designs/asap7/riscv32i:riscv_top
aes @orfs//flow/designs/asap7/aes:aes_cipher_top
riscv32i-mock-sram @orfs//flow/designs/asap7/riscv32i-mock-sram:riscv_top
riscv32i-mock-sram/fakeram @orfs//flow/designs/asap7/riscv32i-mock-sram:fakeram7_256x32
"
STAGES="synth floorplan place cts grt route final"

if [ $# -gt 0 ]; then
  DESIGNS=$(echo "$DESIGNS" | while read -r design target; do
    for name do
      if [ "$design" = "$name" ]; then echo "$design $target"; fi
    done
  done)
fi

targets() {
  echo "$DESIGNS" | while read -r design target; do
    [ -n "$design" ] || continue
    for stage in $STAGES; do
      echo "${target}_$stage"
    done
  done
}

odbs() {
  bazelisk cquery "$@" --output=files 2>/dev/null | grep '\.odb$' || true
}

# Both builds write the same output paths, so the stock files are copied
# aside before the second one replaces them.
out=tmp/odb_codec
rm -rf "$out/stock"
mkdir -p "$out/stock"
pairs=$out/pairs.tsv
: >"$pairs"

bazelisk build --jobs="$JOBS" --//:odb_codec=false $(targets)
echo "$DESIGNS" | while read -r design target; do
  [ -n "$design" ] || continue
  mkdir -p "$out/stock/$design"
  for stage in $STAGES; do
    odbs --//:odb_codec=false "${target}_$stage" | while read -r odb; do
      cp "$odb" "$out/stock/$design/"
      chmod u+w "$out/stock/$design/$(basename "$odb")"
      printf '%s\t%s\t%s\n' "$design" "$out/stock/$design/$(basename "$odb")" "$odb" >>"$pairs"
    done
  done
done

bazelisk build --jobs="$JOBS" $(targets)
bazelisk run //test/odb_codec:measure -- "$pairs" "$out/odb_codec.csv"
