#!/usr/bin/env bash
# Build every pin-wall arm through CTS, install each arm's grt deps tree,
# and run the zero-iteration route on all of them with the grt harness's
# matrix driver. Results in tmp/pinwall/results; the table from
# test/grt_scaling/report.py. Usage: calibrate.sh [output_base] [jobs]
set -u
cd "$(dirname "$0")/../.."
OB=${1:-}
JOBS=${2:-8}
B="bazelisk ${OB:+--output_base=$OB} build --jobs=$JOBS"
R="bazelisk ${OB:+--output_base=$OB} run --jobs=$JOBS"
ARMS=$(bazelisk ${OB:+--output_base=$OB} query '//test/macro_select:all' 2>/dev/null | grep -oE ':pinwall_top_pw_p[0-9]+_c[0-9]+_m[0-9]+_cts$' | sed -E 's#:pinwall_top_(.*)_cts#\1#')
mkdir -p tmp/pinwall/results
echo "arms: $ARMS"
$B $(for a in $ARMS; do echo "//test/macro_select:pinwall_top_${a}_cts //test/macro_select:pinwall_top_${a}_grt_deps"; done) > tmp/pinwall/build.log 2>&1 || { echo "build failed; see tmp/pinwall/build.log"; grep -E "^ERROR" tmp/pinwall/build.log | head -3; }
python3 - "$ARMS" > tmp/pinwall/matrix.json <<'PY'
import json, sys, os
arms = sys.argv[1].split()
designs = {}
for a in arms:
    designs[a] = {"deps": os.path.abspath("tmp/pinwall/%s/deps" % a),
                  "odb": "test/macro_select/results/asap7/pinwall_top/%s/4_cts.odb" % a}
print(json.dumps({"designs": designs,
                  "arms": {"iter0": {"pin_access": False, "args": "-congestion_iterations 0 -allow_congestion"}},
                  "args": "", "timeout_s": 1800, "memory_max": "20G", "swap_max": "20G", "perf": False, "repeats": 1}, indent=1))
PY
for a in $ARMS; do
  mkdir -p tmp/pinwall/$a
  $R //test/macro_select:pinwall_top_${a}_grt_deps -- --install "$PWD/tmp/pinwall/$a/deps" > tmp/pinwall/$a/install.log 2>&1 || echo "install failed: $a"
done
python3 test/grt_scaling/grt_bench.py tmp/pinwall/matrix.json tmp/pinwall/results > tmp/pinwall/bench.log 2>&1
python3 test/grt_scaling/report.py tmp/pinwall/results --baseline iter0 | tee tmp/pinwall/report.md
