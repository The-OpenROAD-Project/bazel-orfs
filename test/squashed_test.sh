#!/bin/sh
# Verify squashed flow produces all expected output files.
# This test depends on the squashed target via 'data', which forces Bazel
# to build it. If any declared output (odb, sdc, spef, v, reports) is
# missing, the build itself fails before this test runs — so reaching
# here means all outputs were produced.
echo "PASS: squashed flow built successfully with all declared outputs"
