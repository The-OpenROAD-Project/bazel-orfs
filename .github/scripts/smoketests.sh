#!/bin/bash
set -ex
rm -rf ./tmp
bazel run //sram:sdq_17x64_mock-naja_floorplan_deps $(pwd)/tmp
ls -l tmp/sram/results/asap7/sdq_17x64/mock-naja/
head -n 5 tmp/sram/results/asap7/sdq_17x64/mock-naja/1_synth.v
grep naja tmp/sram/results/asap7/sdq_17x64/mock-naja/1_synth.v

bazel build lb_32x128_shared_synth_floorplan wns_report //sram:sdq_17x64_mock-naja_floorplan_deps //sram:mock-naja
grep naja bazel-bin/sram/mock-naja.v
grep -q naja bazel-bin/sram/results/asap7/sdq_17x64/mock-naja/1_synth.v && false || true
(bazel build //sram:sdq_17x64_naja-error_floorplan 2>&1 || true) | grep "syntax error"
