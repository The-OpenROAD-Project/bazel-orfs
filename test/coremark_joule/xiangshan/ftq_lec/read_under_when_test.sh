#!/bin/sh
# read_under_when_test.sh CHECK: ReadUnderWhen.scala's elaborations,
# RegVecFile.read ahead of a when and under one; CHECK exits non-zero
# unless the first elaborates and the second stops with its port named.
exec "$1"
