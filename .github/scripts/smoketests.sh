#!/bin/bash
set -ex

echo These targets should have been pruned
bazelisk query //test:* | grep -q -v lb_32x128_1_synth
bazelisk query //test:* | grep -q -v lb_32x128_2_floorplan
bazelisk query //test:* | grep -q -v lb_32x128_3_place
echo This target should exist
bazelisk query //test:* | grep -q -v lb_32x128_4_synth

# orfs_genrule: verify srcs use exec config (not target config)
# Native genrule forces srcs into target config, rebuilding ORFS outputs.
# orfs_genrule keeps srcs in exec config, avoiding the duplicate build.
target_config=$(bazelisk cquery //test:gatelist_wc_orfs_genrule 2>&1 | grep "^//" | sed 's/.*(\(.*\))/\1/')
srcs_config=$(bazelisk cquery 'deps(//test:gatelist_wc_orfs_genrule, 1)' 2>&1 | grep "gatelist " | sed 's/.*(\(.*\))/\1/')
test "$target_config" != "$srcs_config"

bazelisk test ... \
   --keep_going \
   --test_output=errors \
   --profile=build.profile

# Reenable naja tests later, merged.lib is gone, PRs welcome...
#
# grep naja bazel-bin/sram/mock-naja.v
# grep -q naja bazel-bin/sram/results/asap7/sdq_17x64/mock-naja/1_synth.v && false || true
# (bazelisk build //sram:sdq_17x64_naja-error_floorplan 2>&1 || true) | grep "syntax error"

# bazelisk run //sram:sdq_17x64_mock-naja_floorplan_deps
# grep naja tmp/sram/_main/sram/results/asap7/sdq_17x64/mock-naja/1_synth.v

bazelisk analyze-profile build.profile
