#!/bin/sh
# The certificate's three steps, POSIX sh and awk only.
#
#   cert.sh closure <split dir> <top> <out.sv> <out manifest>
#       the modules reachable from <top> in firtool's one-file-per-module
#       output, each file unchanged, concatenated in name order with the
#       `include lines dropped (every included file is in the set)
#   cert.sh generate <CoupledL2.sv> <manifest>
#       (bazelisk run //:generate) copies them into generated/ here
#   cert.sh lec
#       (bazelisk run //:lec) the equivalence proof; not available yet
set -eu
# The module order is part of the output: sort the same everywhere.
export LC_ALL=C

closure() {
  dir=$1 top=$2 out=$3 manifest=$4
  # module name -> file, from the module headers
  index=$(mktemp)
  for f in "$dir"/*.sv; do
    awk -v f="$f" '/^[ \t]*module[ \t]+[A-Za-z_][A-Za-z_0-9$]*/ {
      n = $0; sub(/^[ \t]*module[ \t]+/, "", n); sub(/[^A-Za-z_0-9$].*$/, "", n); print n, f }' "$f"
  done | sort -u > "$index"
  grep -q "^$top " "$index" || { echo "cert.sh: no module $top in $dir" >&2; exit 1; }
  seen=$(mktemp) pending=$(mktemp)
  echo "$top" > "$pending"
  : > "$seen"
  while [ -s "$pending" ]; do
    name=$(head -n 1 "$pending"); sed -i '1d' "$pending"
    grep -qx "$name" "$seen" && continue
    echo "$name" >> "$seen"
    file=$(awk -v n="$name" '$1 == n { print $2; exit }' "$index")
    # an instance is `Foo foo (` or `Foo #(...) foo (` at the start of a
    # line, indented at least two spaces; keywords in that position are not
    awk '/^  +[A-Za-z_][A-Za-z_0-9$]*[ \t]+(#\(.*\)[ \t]*)?[A-Za-z_]/ {
      n = $1
      if (n !~ /^(always|always_comb|always_ff|always_latch|and|assign|assert|assume|automatic|begin|case|casex|casez|default|else|end|endcase|endfunction|endgenerate|endmodule|for|function|generate|genvar|if|initial|inout|input|integer|localparam|logic|module|nand|negedge|nor|not|or|output|parameter|posedge|reg|signed|typedef|unsigned|wire|xnor|xor)$/) print n
    }' "$file" | sort -u | while read -r m; do
      if grep -q "^$m " "$index" && ! grep -qx "$m" "$seen"; then echo "$m" >> "$pending"; fi
    done
  done
  sort "$seen" | while read -r m; do
    grep -hvF '`include' "$(awk -v n="$m" '$1 == n { print $2; exit }' "$index")"
  done > "$out"
  { echo "top: $top"; echo "modules: $(wc -l < "$seen")"; sort "$seen" | sed 's/^/  /'; } > "$manifest"
  rm -f "$index" "$seen" "$pending"
}

case "$1" in
  closure) shift; closure "$@" ;;
  generate)
    dest="${BUILD_WORKSPACE_DIRECTORY:?run through bazelisk run //:generate}/generated"
    mkdir -p "$dest"
    cp -f "$2" "$dest/CoupledL2.sv"
    cp -f "$3" "$dest/MANIFEST"
    chmod u+w "$dest/CoupledL2.sv" "$dest/MANIFEST"
    echo "wrote $dest/CoupledL2.sv ($(wc -l < "$dest/CoupledL2.sv") lines) and $dest/MANIFEST"
    ;;
  lec)
    echo "LEC is not available yet: kepler-formal does not build natively in Bazel." >&2
    echo "Nothing has been proven; this is not a pass." >&2
    exit 1
    ;;
  *) echo "usage: cert.sh closure|generate|lec" >&2; exit 2 ;;
esac
