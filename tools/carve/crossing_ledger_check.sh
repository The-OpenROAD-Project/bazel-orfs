#!/bin/sh
# The crossing ledger's check against the top level
# (crossing_ledger_check.py), and its negative controls: the check must
# fail, and for the reason given, with a part's halves at zero and with a
# block's ledger gone.
#
# Usage: crossing_ledger_check.sh <crossing_ledger_check> <control>
#            <max skew ps> <top.txt> <hub ledger> <block>=<ledger>...
#        crossing_ledger_check.sh <crossing_ledger_check> same <ledger> <ledger>
#
# control: - for the check itself, with the hub's spot checks and miss
# count; all for the negative controls, every part in turn; same for two
# ledgers of one part that must hold the same halves.
set -e
check="$1"
control="$2"
shift 2
if [ "$control" = same ]; then
  exec "$check" --same "$1" "$2"
fi
skew="$1"
top="$2"
hub="$3"
shift 3
blocks=""
for b in "$@"; do
  blocks="$blocks --block $b"
done
if [ "$control" = - ]; then
  # shellcheck disable=SC2086
  exec "$check" --top "$top" --hub "$hub" $blocks --max-skew "$skew" --spot --miss
fi

out="${TEST_TMPDIR:-$(mktemp -d)}/ledger_check.txt"

# must_fail <what> <message> <option> <part>: the check fails, saying so
must_fail() {
  # shellcheck disable=SC2086
  if "$check" --top "$top" --hub "$hub" $blocks --max-skew "$skew" "$3" "$4" > "$out" 2>&1; then
    echo "the check passed with $1:"
    cat "$out"
    exit 1
  fi
  if ! grep -q "$2" "$out"; then
    echo "the check failed with $1, and not for that:"
    cat "$out"
    exit 1
  fi
  echo "with $1 the check fails: $(grep "$2" "$out" | head -1 | cut -c1-240)"
}

must_fail "the hub's halves at zero" "ledger under the top level.* u_" --zero hub
for b in "$@"; do
  m="${b%%=*}"
  must_fail "$m's halves at zero" "ledger under the top level.* u_${m}__" --zero "$m"
  must_fail "$m's ledger gone" "no ledger for block $m" --drop "$m"
done
