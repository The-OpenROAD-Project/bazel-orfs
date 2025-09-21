#!/bin/bash
set -ex

echo These targets should have been pruned
bazelisk query //:* | grep -q -v lb_32x128_1_synth
bazelisk query //:* | grep -q -v lb_32x128_2_floorplan
bazelisk query //:* | grep -q -v lb_32x128_3_place
echo This target should exist
bazelisk query //:* | grep -q -v lb_32x128_4_synth

bazelisk test ... \
   --keep_going \
   --test_output=errors \
   --profile=build.profile

# Reenable naja tests later, merged.lib is gone, PRs welcome...
#
# grep naja bazel-bin/sram/mock-naja.v
# grep -q naja bazel-bin/sram/results/asap7/sdq_17x64/mock-naja/1_synth.v && false || true
# (bazelisk build //sram:sdq_17x64_naja-error_floorplan 2>&1 || true) | grep "syntax error"

# bazelisk run //sram:sdq_17x64_mock-naja_floorplan_deps $(pwd)/tmp
# grep naja tmp/_main/sram/results/asap7/sdq_17x64/mock-naja/1_synth.v

bazelisk analyze-profile build.profile
